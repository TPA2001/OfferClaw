"""授权密钥模块测试

覆盖：签发→验签、过期、机器绑定、功能分级、篡改拒绝、激活缓存(保存/加载/清除)
"""
import time
import pytest
import jwt
from cryptography.hazmat.primitives import serialization

from app.core import license as L


# ── 测试用私钥（与 license.py 内嵌公钥配对；从 data/license_keys/private.pem 读取）──
@pytest.fixture(scope="module")
def private_key():
    from pathlib import Path
    pem = Path("data/license_keys/private.pem").read_bytes()
    return serialization.load_pem_private_key(pem, password=None)


def _make_token(private_key, *, exp_delta=3600, features=None, machine="", customer="测试", product="offerclaw"):
    now = int(time.time())
    payload = {
        "iss": "offerclaw", "sub": "test-lid", "iat": now, "exp": now + exp_delta,
        "product": product, "customer": customer,
        "features": features if features is not None else ["*"],
        "machine": machine,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


class TestVerify:
    def test_valid_token(self, private_key):
        t = _make_token(private_key)
        info = L.verify_license(t, check_machine=False)
        assert info.customer == "测试"
        assert info.has_feature("smart_fill")
        assert not info.is_expired()

    def test_expired_rejected(self, private_key):
        t = _make_token(private_key, exp_delta=-10)
        with pytest.raises(L.LicenseError) as exc:
            L.verify_license(t, check_machine=False)
        assert exc.value.code == "expired"

    def test_invalid_signature(self, private_key):
        t = _make_token(private_key)
        # 篡改签名末尾
        with pytest.raises(L.LicenseError) as exc:
            L.verify_license(t[:-5] + "AAAAA", check_machine=False)
        assert exc.value.code == "invalid"

    def test_wrong_product(self, private_key):
        t = _make_token(private_key, product="other-product")
        with pytest.raises(L.LicenseError) as exc:
            L.verify_license(t, check_machine=False)
        assert exc.value.code == "invalid"

    def test_empty_token(self):
        with pytest.raises(L.LicenseError) as exc:
            L.verify_license("", check_machine=False)
        assert exc.value.code == "invalid"

    def test_machine_binding_mismatch(self, private_key):
        t = _make_token(private_key, machine="wrongfingerprint1")
        with pytest.raises(L.LicenseError) as exc:
            L.verify_license(t, check_machine=True)
        assert exc.value.code == "machine_mismatch"

    def test_machine_unbound_ok(self, private_key):
        # machine="" 表示不绑定，应通过
        t = _make_token(private_key, machine="")
        info = L.verify_license(t, check_machine=True)
        assert info.machine == ""

    def test_feature_tiering(self, private_key):
        t = _make_token(private_key, features=["smart_fill"])
        info = L.verify_license(t, check_machine=False)
        assert info.has_feature("smart_fill")
        assert not info.has_feature("agent")
        assert not info.has_feature("dashboard")

    def test_star_feature_grants_all(self, private_key):
        t = _make_token(private_key, features=["*"])
        info = L.verify_license(t, check_machine=False)
        assert info.has_feature("smart_fill") and info.has_feature("agent")


class TestActivationCache:
    def test_save_load_clear(self, private_key, tmp_path, monkeypatch):
        # 把激活文件指向临时目录，避免污染 data/license.dat
        tmp_file = tmp_path / "license.dat"
        monkeypatch.setattr(L, "LICENSE_FILE", tmp_file)
        # 清空进程缓存为未激活态
        L._current_license = None

        t = _make_token(private_key, machine="")
        info = L.save_activation(t)
        assert info.customer == "测试"
        assert tmp_file.exists()

        # 加载
        loaded = L.load_activation()
        assert loaded is not None
        assert loaded.customer == "测试"

        # 清除
        L.clear_activation()
        assert not tmp_file.exists()
        assert L.load_activation() is None

    def test_load_expired_returns_none(self, private_key, tmp_path, monkeypatch):
        tmp_file = tmp_path / "license.dat"
        monkeypatch.setattr(L, "LICENSE_FILE", tmp_file)
        L._current_license = None
        t = _make_token(private_key, exp_delta=-10, machine="")
        tmp_file.write_text(t, encoding="utf-8")
        assert L.load_activation() is None  # 过期 → None


class TestGate:
    def test_dev_mode_bypass(self, monkeypatch):
        monkeypatch.setenv("OFFERCLAW_DEV", "1")
        assert L.is_dev_mode() is True
        assert L.is_activated() is True
        assert L.is_feature_enabled("agent") is True

    def test_require_feature_for_path(self):
        assert L.require_feature_for_path("/api/v1/automation/x") == L.FEATURE_SMART_FILL
        assert L.require_feature_for_path("/api/v1/agent/run") == L.FEATURE_AGENT
        assert L.require_feature_for_path("/api/v1/profiles") is None  # 核心功能
