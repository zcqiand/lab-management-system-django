"""SaaS 多租户多应用身份平台 HTTP 客户端 —— lab-springboot SaasAuthClient/SaasMeClient 镜像
（fastapi impl/saas_client.py 同源）。

- SaasAuthClient：服务账号登录（POST /api/v1/auth/login）+ token 端点
  （POST /api/v1/oauth/token，grantType=authorization_code|refresh_token）；
  错误分流 saas 401 → UnauthorizedClientError / 其他 4xx → InvalidGrantError /
  5xx 与连接失败 → SaasUpstreamError
- SaasMeClient：/me、/me/tenants、/me/menus（Map<appCode,tree> 取子树）、
  /admin/tenants（租户显示名富化）；4xx → InvalidGrantError、5xx/连接 → SaasUpstreamError

单测不真连：测试以 fake 注入 ``authn.state.registry.saas_auth/saas_me`` 缝，本模块
仅在生产 registry 实例化；saas 真连验证归 T11 contract-test live。
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, Field

from authn.config import AuthConfig
from authn.errors import InvalidGrantError, SaasUpstreamError, UnauthorizedClientError

_TIMEOUT_SECONDS = 10.0


class TokenResponse(BaseModel):
    """saas token 端点响应子集（accessToken/refreshToken）。"""

    access_token: str
    refresh_token: str


class _SaasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SaasCurrentUser(_SaasModel):
    """saas GET /api/v1/me 响应。"""

    id: str
    email: str
    display_name: str | None = Field(default=None, alias="displayName")
    current_tenant_id: str | None = Field(default=None, alias="currentTenantId")


class SaasTenantMembership(_SaasModel):
    """saas GET /api/v1/me/tenants 行（契约只有 tenantId，不带名）。"""

    tenant_id: str = Field(alias="tenantId")
    role_ids: list[str] = Field(default_factory=list, alias="roleIds")


class SaasMenuNode(_SaasModel):
    """saas /me/menus 节点。名称字段是 ``title`` 不是 name（家族实测 payload 修正）。"""

    id: str
    code: str | None = None
    title: str | None = None
    path: str | None = None
    icon: str | None = None
    type: str | None = None
    sort_order: int | None = Field(default=None, alias="sortOrder")
    children: list[SaasMenuNode] = Field(default_factory=list)


class SaasPlatformTenant(_SaasModel):
    """saas GET /api/v1/admin/tenants 行（guard 只验 JWT，任何登录用户可读）。"""

    id: str
    name: str | None = None
    tenant_key: str | None = Field(default=None, alias="tenantKey")


class SaasLoginUser(_SaasModel):
    """saas POST /api/v1/auth/login 响应 user 段（REQ-2026-023）。

    saas 侧 displayName 可为空串——回退链必须 falsy 语义，不能 is-not-None 判断
    （家族记忆 saas-no-displayname-empty-string-fallback-trap）。
    """

    id: str
    username: str | None = None
    email: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")


class SaasAvailableTenant(_SaasModel):
    """userLogin 响应 availableTenants 行：只有 tenantId+roleIds，无租户名。"""

    tenant_id: str = Field(alias="tenantId")
    role_ids: list[str] = Field(default_factory=list, alias="roleIds")
    status: str | None = None


class SaasLoginResponse(_SaasModel):
    """saas POST /api/v1/auth/login 响应全形（REQ-2026-023 登录代理出站）。"""

    user: SaasLoginUser | None = None
    available_tenants: list[SaasAvailableTenant] = Field(
        default_factory=list, alias="availableTenants"
    )
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(default="", alias="refreshToken")
    user_id: str | None = Field(default=None, alias="userId")
    current_tenant_id: str | None = Field(default=None, alias="currentTenantId")


def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _raise_for_saas_status(status_code: int, body: str, endpoint: str) -> None:
    detail = f"saas {endpoint} {status_code} {_truncate(body)}"
    if status_code == 401:
        raise UnauthorizedClientError(detail)
    if 400 <= status_code < 500:
        raise InvalidGrantError(detail)
    raise SaasUpstreamError(f"saas {endpoint} 5xx: {status_code}")


def _as_list(payload: object, endpoint: str) -> list[object]:
    if not isinstance(payload, list):
        raise SaasUpstreamError(f"saas {endpoint} unexpected payload shape")
    return payload


class SaasAuthClient:
    def __init__(self, config: AuthConfig | None = None) -> None:
        self._config = config if config is not None else _config_from_registry()

    def user_login(self, username: str, password: str) -> SaasLoginResponse:
        """原生登录账密校验出站（REQ-2026-023）：账密原值透传，
        clientId=OAuth client id（LAB_SAAS_CLIENT_ID）——与 service_login 分流。"""
        payload = self._request_json(
            "/api/v1/auth/login",
            json_body={
                "username": username,
                "password": password,
                "clientId": self._config.saas_client_id,
            },
            endpoint="auth/login",
        )
        return SaasLoginResponse.model_validate(payload)

    def service_login(self) -> TokenResponse:
        """服务账号登录（密码登录用户菜单快照路径）。"""
        payload = self._request_json(
            "/api/v1/auth/login",
            json_body={
                "username": self._config.saas_service_user,
                "password": self._config.saas_service_password,
                "clientId": self._config.saas_service_client_id,
            },
            endpoint="auth/login",
        )
        return self._token_from(payload, "auth/login")

    def token(
        self,
        grant_type: str,
        code: str | None = None,
        refresh_token: str | None = None,
        redirect_uri: str | None = None,
    ) -> TokenResponse:
        """OAuth token 端点；body 字段名 camelCase 镜像 springboot。"""
        body: dict[str, str] = {
            "grantType": grant_type,
            "clientId": self._config.saas_client_id,
            "clientSecret": self._config.saas_client_secret,
            "tenantId": self._config.saas_default_tenant_id,
        }
        if code is not None:
            body["code"] = code
        if refresh_token is not None:
            body["refreshToken"] = refresh_token
        if redirect_uri is not None:
            body["redirectUri"] = redirect_uri
        payload = self._request_json("/api/v1/oauth/token", json_body=body, endpoint="oauth/token")
        return self._token_from(payload, "oauth/token")

    def _request_json(
        self, path: str, json_body: dict[str, str], endpoint: str
    ) -> dict[str, object]:
        """POST 出站公共段：连接失败/4xx/5xx 归类（镜像 springboot），返回解析 dict。"""
        try:
            resp = httpx.request(
                "POST",
                self._config.saas_base_url + path,
                json=json_body,
                timeout=_TIMEOUT_SECONDS,
            )
        except httpx.TransportError as exc:
            raise SaasUpstreamError(f"saas {endpoint} connect failed: {exc}") from exc
        if resp.status_code >= 400:
            _raise_for_saas_status(resp.status_code, resp.text, endpoint)
        payload = resp.json()
        if not isinstance(payload, dict):
            raise SaasUpstreamError(f"saas {endpoint} unexpected payload shape")
        return payload

    @staticmethod
    def _token_from(payload: dict[str, object], endpoint: str) -> TokenResponse:
        if "accessToken" not in payload:
            raise SaasUpstreamError(f"saas {endpoint} unexpected payload shape")
        return TokenResponse(
            access_token=str(payload["accessToken"]),
            refresh_token=str(payload.get("refreshToken", "")),
        )


class SaasMeClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = base_url if base_url is not None else _config_from_registry().saas_base_url

    def whoami(self, access_token: str) -> SaasCurrentUser:
        payload = self._get_json("/api/v1/me", access_token, "me")
        return SaasCurrentUser.model_validate(payload)

    def list_my_tenants(self, access_token: str) -> list[SaasTenantMembership]:
        rows = _as_list(
            self._get_json("/api/v1/me/tenants", access_token, "me/tenants"), "me/tenants"
        )
        return [SaasTenantMembership.model_validate(row) for row in rows]

    def list_my_menus(self, access_token: str, app_code: str) -> list[SaasMenuNode]:
        """GET /api/v1/me/menus → Map<appCode, tree>，按 appCode 取子树。"""
        payload = self._get_json("/api/v1/me/menus", access_token, "me/menus")
        tree: object = []
        if isinstance(payload, dict):
            tree = payload.get(app_code) or []
        return [SaasMenuNode.model_validate(node) for node in _as_list(tree, "me/menus")]

    def list_platform_tenants(self, access_token: str) -> list[SaasPlatformTenant]:
        payload = self._get_json(
            "/api/v1/admin/tenants?page=0&pageSize=100", access_token, "admin/tenants"
        )
        rows: object = []
        if isinstance(payload, dict):
            rows = payload.get("items") or []
        return [SaasPlatformTenant.model_validate(row) for row in _as_list(rows, "admin/tenants")]

    def _get_json(self, path: str, access_token: str, endpoint: str) -> object:
        try:
            resp = httpx.request(
                "GET",
                self._base + path,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=_TIMEOUT_SECONDS,
            )
        except httpx.TransportError as exc:
            raise SaasUpstreamError(f"saas {endpoint} connect failed: {exc}") from exc
        if resp.status_code >= 400:
            _raise_for_saas_status(resp.status_code, resp.text, endpoint)
        return resp.json()


def _config_from_registry() -> AuthConfig:
    # 延迟 import 避免模块环（state → saas_client 构造需要 config）
    from authn.config import AuthConfig  # noqa: PLC0415

    return AuthConfig.from_env()
