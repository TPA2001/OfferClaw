"""
OfferCabin 集中配置管理

使用 Pydantic Settings 统一管理环境变量配置，
替代散落在各模块的 os.getenv 调用。

用法:
    from app.core.config import settings
    settings.database_url
    settings.auth_mode
    settings.agent_model
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """OfferCabin 应用配置（从环境变量 / .env 文件加载）"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略未定义的环境变量
    )

    # ===== 应用 =====
    app_name: str = "OfferCabin"
    app_version: str = "0.0.2"
    debug: bool = Field(default=False, alias="APP_DEBUG")

    # ===== 数据库 =====
    database_url: str = Field(
        default="sqlite:///./offercabin.db",
        alias="DATABASE_URL",
    )

    # ===== 鉴权 =====
    # jwt = 多用户账号模式（网页服务默认）；open = 单用户本地模式（仅本地开发）
    auth_mode: str = Field(default="jwt", alias="AUTH_MODE")
    secret_key: str = Field(default="dev-secret-key-12345", alias="SECRET_KEY")
    # 访问令牌有效期（小时），默认 7 天
    auth_token_ttl_hours: int = Field(default=168, alias="AUTH_TOKEN_TTL_HOURS")
    # 注册邀请码（设置后注册必须携带；用于账号售卖场景控制注册入口）
    registration_invite_code: Optional[str] = Field(default=None, alias="REGISTRATION_INVITE_CODE")
    # 找回密码令牌直接随响应返回（仅限内网调试，生产保持关闭）
    auth_reset_token_in_response: bool = Field(default=False, alias="AUTH_RESET_TOKEN_IN_RESPONSE")

    # ===== CORS =====
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000",
        alias="CORS_ORIGINS",
    )

    # ===== 管理后台（独立端口，与公开应用隔离）=====
    # 管理后台默认绑 127.0.0.1：仅本机可达，Docker 内需设 0.0.0.0 并通过宿主 127.0.0.1:8001 映射隔离
    admin_host: str = Field(default="127.0.0.1", alias="ADMIN_HOST")
    admin_port: int = Field(default=8001, alias="ADMIN_PORT")
    # 管理后台 CORS：默认仅放行管理端口本地来源
    admin_cors_origins: str = Field(
        default="http://localhost:8001,http://127.0.0.1:8001",
        alias="ADMIN_CORS_ORIGINS",
    )
    # 管理端口 IP 白名单（逗号分隔，留空则放行；建议生产显式配置）
    admin_allow_ips: Optional[str] = Field(default=None, alias="ADMIN_ALLOW_IPS")
    # 管理员令牌有效期（小时），短于普通用户令牌，默认 12 小时
    admin_token_ttl_hours: int = Field(default=12, alias="ADMIN_TOKEN_TTL_HOURS")

    # ===== LLM Provider 选择 =====
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")

    # ===== Agent 编排模型（强模型） =====
    agent_api_key: Optional[str] = Field(default=None, alias="AGENT_API_KEY")
    agent_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        alias="AGENT_BASE_URL",
    )
    agent_model: str = Field(default="glm-4.5", alias="AGENT_MODEL")

    # ===== 内容生成模型（快模型，可选） =====
    gen_api_key: Optional[str] = Field(default=None, alias="GEN_API_KEY")
    gen_base_url: Optional[str] = Field(default=None, alias="GEN_BASE_URL")
    gen_model: Optional[str] = Field(default=None, alias="GEN_MODEL")

    # ===== 兼容旧配置（OPENAI_*） =====
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="OPENAI_BASE_URL",
    )
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # ===== LLM 重试 =====
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")

    # ===== 可观测性 / Tracing =====
    # 全局开关：true 时记录每次 Agent 运行的追踪事件到本地 JSONL
    trace_enabled: bool = Field(default=True, alias="TRACE_ENABLED")
    # 导出器：local（本地 JSONL）| langsmith（远程 LangSmith）
    trace_exporter: str = Field(default="local", alias="TRACE_EXPORTER")
    # 本地追踪日志目录（相对 data 目录）
    trace_dir: str = Field(default="traces", alias="TRACE_DIR")

    # ===== LangSmith（可选，trace_exporter=langsmith 时生效）=====
    langsmith_api_key: Optional[str] = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="offercabin", alias="LANGSMITH_PROJECT")
    langsmith_endpoint: Optional[str] = Field(default=None, alias="LANGSMITH_ENDPOINT")

    # ===== 计算属性 =====

    @computed_field  # type: ignore[misc]
    @property
    def cors_origin_list(self) -> list[str]:
        """CORS 来源列表"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def allow_credentials(self) -> bool:
        """是否允许携带凭证（通配符时必须关闭）"""
        return "*" not in self.cors_origin_list

    @computed_field  # type: ignore[misc]
    @property
    def admin_cors_origin_list(self) -> list[str]:
        """管理后台 CORS 来源列表"""
        return [o.strip() for o in self.admin_cors_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def admin_allow_credentials(self) -> bool:
        """管理后台是否允许携带凭证（通配符时必须关闭）"""
        return "*" not in self.admin_cors_origin_list

    @computed_field  # type: ignore[misc]
    @property
    def admin_allow_ip_list(self) -> list[str]:
        """管理端口 IP 白名单（已去重、去空）"""
        if not self.admin_allow_ips:
            return []
        return list({ip.strip() for ip in self.admin_allow_ips.split(",") if ip.strip()})

    @computed_field  # type: ignore[misc]
    @property
    def effective_agent_api_key(self) -> Optional[str]:
        """实际使用的 Agent API Key（优先 AGENT_*，回退 OPENAI_*）"""
        return self.agent_api_key or self.openai_api_key

    @computed_field  # type: ignore[misc]
    @property
    def effective_agent_base_url(self) -> str:
        """实际使用的 Agent Base URL"""
        if self.agent_api_key:
            return self.agent_base_url
        return self.openai_base_url

    @computed_field  # type: ignore[misc]
    @property
    def effective_agent_model(self) -> str:
        """实际使用的 Agent 模型"""
        if self.agent_api_key:
            return self.agent_model
        return self.openai_model

    @computed_field  # type: ignore[misc]
    @property
    def effective_gen_api_key(self) -> Optional[str]:
        """内容生成 API Key（未配置 GEN_* 时复用 Agent）"""
        return self.gen_api_key or self.effective_agent_api_key

    @computed_field  # type: ignore[misc]
    @property
    def effective_gen_base_url(self) -> str:
        """内容生成 Base URL"""
        if self.gen_api_key:
            return self.gen_base_url or self.agent_base_url
        return self.effective_agent_base_url

    @computed_field  # type: ignore[misc]
    @property
    def effective_gen_model(self) -> str:
        """内容生成模型"""
        if self.gen_api_key:
            return self.gen_model or "glm-4-flash"
        return self.effective_agent_model

    @computed_field  # type: ignore[misc]
    @property
    def llm_configured(self) -> bool:
        """LLM 是否已配置真实 API Key"""
        return self.effective_agent_api_key is not None


@lru_cache
def get_settings() -> Settings:
    """获取配置单例（lru_cache 确保全局唯一）"""
    return Settings()


# 全局配置实例
settings = get_settings()
