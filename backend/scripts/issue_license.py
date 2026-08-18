"""OfferClaw 授权密钥签发 CLI（开发者专用）

用法示例：
  # 1. 查看本机指纹（把此指纹报给开发者，或用户自取后报给你）
  python scripts/issue_license.py --my-machine

  # 2. 签发全功能 1 年密钥（不绑机器）
  python scripts/issue_license.py --customer "张三" --days 365 --features "*"

  # 3. 签发智能填写+Agent 半年密钥，绑机器指纹 a1b2c3d4e5f67890
  python scripts/issue_license.py -c "张三" -d 180 -f smart_fill,agent -m a1b2c3d4e5f67890

  # 4. 指定到期日
  python scripts/issue_license.py -c "张三" --exp 2026-12-31 -f "*"

注意：
  - 私钥位于 data/license_keys/private.pem，切勿随产品分发！
  - 公钥已嵌入 app/core/license.py，用户端仅能验签不能伪造。
"""
import argparse
import sys
import uuid
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization

# 私钥路径（开发者本地持有，不随产品分发）
DEFAULT_PRIVATE_KEY = Path("data/license_keys/private.pem")
# 内嵌的公钥（与 app/core/license.py 保持一致，用于签发后自校验）
PRODUCT_PUBLIC_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA6RFQEiVpZY4/x4HvEiyp
aVgpIAOJbJ05+/QgoBJhlscqFvkRcGxVtioIQJEy08jjeGo90xNg2X6vgfog95F6
sRV49HaD7TBhHkFLuSafvS2ceDzQxvp59Aq6L+QeWCYZIpOXpeTNXB8KdgZCEvqu
ToeBnwno2W6xLGVqWrIOKsNDAe7rZ6z9yM9ziOqsVnNkOBF8IJef1ABqvnoG4JgX
p15suH7VMRk/Yu1rZxhyCpv81qJPRk4V+rNA8GL7ocAd4g74MYQs9izitbPDffih
pqqoEpVZMSHl0CfL+f6QuhJhcIIw6sf+6cwXkmWevOHMwAOMPOO9N9VGrz2A/aHA
gwIDAQAB
-----END PUBLIC KEY-----"""


def load_private_key(path: Path):
    if not path.exists():
        print(f"[错误] 私钥不存在：{path}", file=sys.stderr)
        print("请先生成密钥对：参考 app/core/license.py 顶部公钥对应的私钥生成。", file=sys.stderr)
        sys.exit(1)
    pem = path.read_bytes()
    from cryptography.hazmat.primitives.asymmetric import rsa
    return serialization.load_pem_private_key(pem, password=None)


def parse_expiry(args) -> int:
    """返回到期 unix 时间戳"""
    if args.exp:
        dt = datetime.strptime(args.exp, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt = dt + timedelta(days=1) - timedelta(seconds=1)  # 到当天 23:59:59
    else:
        days = args.days or 365
        dt = datetime.now(timezone.utc) + timedelta(days=days)
    return int(dt.timestamp())


def main():
    ap = argparse.ArgumentParser(description="OfferClaw 授权密钥签发 CLI")
    ap.add_argument("-c", "--customer", help="客户名")
    ap.add_argument("-d", "--days", type=int, help="有效天数（默认 365）")
    ap.add_argument("--exp", help="到期日 YYYY-MM-DD（与 --days 二选一）")
    ap.add_argument(
        "-f", "--features", default="*",
        help="功能列表，逗号分隔；* 表示全部（smart_fill,agent,dashboard）",
    )
    ap.add_argument("-m", "--machine", default="", help="绑定的机器指纹（空=不绑定）")
    ap.add_argument("--key", default=str(DEFAULT_PRIVATE_KEY), help="私钥路径")
    ap.add_argument("--my-machine", action="store_true", help="打印本机指纹后退出")
    ap.add_argument("--no-verify", action="store_true", help="跳过签发后自校验")
    args = ap.parse_args()

    # 仅查本机指纹
    if args.my_machine:
        # 复用 license 模块的指纹算法（避免导入 app 受环境变量影响）
        import hashlib, platform
        node = uuid.getnode()
        raw = f"{node}|{platform.node()}|{platform.machine()}|{platform.processor()}"
        fp = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        print("本机授权指纹（报给开发者签发机器绑定密钥）：")
        print(fp)
        return

    if not args.customer:
        ap.error("--customer 必填")

    priv = load_private_key(Path(args.key))

    features = [f.strip() for f in args.features.split(",") if f.strip()]
    now = int(time.time())
    exp = parse_expiry(args)
    payload = {
        "iss": "offerclaw",
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": exp,
        "product": "offerclaw",
        "customer": args.customer,
        "features": features,
        "machine": args.machine or "",
    }

    token = jwt.encode(payload, priv, algorithm="RS256")

    # 自校验：用内嵌公钥验签
    if not args.no_verify:
        try:
            jwt.decode(token, PRODUCT_PUBLIC_PEM, algorithms=["RS256"], options={"verify_aud": False})
        except Exception as e:
            print(f"[错误] 签发后自校验失败：{e}", file=sys.stderr)
            sys.exit(1)

    print("===== OfferClaw 授权密钥（分发给用户）=====")
    print(token)
    print()
    print("===== 密钥信息 =====")
    print(f"客户：{args.customer}")
    print(f"功能：{', '.join(features)}")
    print(f"到期：{datetime.fromtimestamp(exp, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"机器绑定：{args.machine or '不绑定'}")
    print(f"License ID：{payload['sub']}")


if __name__ == "__main__":
    main()
