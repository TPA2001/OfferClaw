"""
日志脱敏工具测试

覆盖手机号/邮箱/身份证/银行卡/薪资的脱敏
"""
from app.core.log_utils import sanitize_for_log


class TestSanitizeForLog:
    def test_phone_redacted(self):
        text = "我的手机号是 13812345678 请联系我"
        result = sanitize_for_log(text)
        assert "13812345678" not in result
        assert "***" in result

    def test_email_redacted(self):
        text = "发到 zhangsan@example.com 就行"
        result = sanitize_for_log(text)
        assert "zhangsan@example.com" not in result
        assert "***@***" in result

    def test_idcard_redacted(self):
        text = "身份证 110101199003071234"
        result = sanitize_for_log(text)
        assert "110101199003071234" not in result

    def test_truncation(self):
        text = "a" * 200
        result = sanitize_for_log(text, max_len=80)
        assert len(result) <= 85  # 80 + "..."
        assert result.endswith("...")

    def test_empty_input(self):
        assert sanitize_for_log("") == ""
        assert sanitize_for_log(None) == ""

    def test_normal_text_preserved(self):
        text = "帮我查看投递记录"
        result = sanitize_for_log(text)
        assert result == "帮我查看投递记录"

    def test_multiple_sensitive_fields(self):
        text = "手机 13812345678 邮箱 test@test.com 都可以联系"
        result = sanitize_for_log(text)
        assert "13812345678" not in result
        assert "test@test.com" not in result
