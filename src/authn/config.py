"""authn 域配置 —— env fail-fast，无默认值兜底（suite 硬规则 §1）。

键面镜像 lab-fastapi impl/config.py（其镜像 lab-springboot application.yml ``lab:``
段）。DATABASE_URL 不在此（django settings 拥有）；LAB_SSO_LOGIN_URL 是唯一非
fail-fast 键：空回落 saas base 是家族语义（springboot effectiveLoginUrl javadoc——
dev 时 saas-nextjs 同源），不是 env 缺省兜底。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if value is None or value == "":
        raise RuntimeError(f"env {key} required（禁默认值兜底，suite 硬规则 §1）")
    return value


@dataclass(frozen=True)
class AuthConfig:
    jwt_signing_key: str
    jwt_issuer: str
    jwt_ttl_seconds: int
    jwt_refresh_ttl_seconds: int
    saas_base_url: str
    sso_login_url: str
    saas_client_id: str
    saas_client_secret: str
    saas_default_tenant_id: str
    sso_callback_redirect: str
    saas_service_user: str
    saas_service_password: str
    saas_service_client_id: str
    cors_allowed_origins: str

    @property
    def effective_login_url(self) -> str:
        """saas IdP 登录页 base：``{loginUrl}/login?...``；空回落 saas base（家族语义）。"""
        return self.sso_login_url if self.sso_login_url.strip() else self.saas_base_url

    @classmethod
    def from_env(cls) -> AuthConfig:
        return cls(
            jwt_signing_key=_require_env("JWT_SIGNING_KEY"),
            jwt_issuer=_require_env("JWT_ISSUER"),
            jwt_ttl_seconds=int(_require_env("JWT_TTL_SECONDS")),
            jwt_refresh_ttl_seconds=int(_require_env("JWT_REFRESH_TTL_SECONDS")),
            saas_base_url=_require_env("LAB_SAAS_BASE_URL"),
            sso_login_url=os.environ.get("LAB_SSO_LOGIN_URL", ""),
            saas_client_id=_require_env("LAB_SAAS_CLIENT_ID"),
            saas_client_secret=_require_env("LAB_SAAS_CLIENT_SECRET"),
            saas_default_tenant_id=_require_env("LAB_SAAS_DEFAULT_TENANT_ID"),
            sso_callback_redirect=_require_env("LAB_SSO_CALLBACK_REDIRECT"),
            saas_service_user=_require_env("LAB_SAAS_SERVICE_USER"),
            saas_service_password=_require_env("LAB_SAAS_SERVICE_PASSWORD"),
            saas_service_client_id=_require_env("LAB_SAAS_SERVICE_CLIENT_ID"),
            cors_allowed_origins=_require_env("LAB_CORS_ALLOWED_ORIGINS"),
        )
