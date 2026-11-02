"""authn 域服务 —— 认证域 10 端点实现，语义逐条对照 lab-fastapi impl/auth_impl.py
（其注释标注参照 lab-springboot AuthService.java）。

响应直接落契约 dict 形（键名 camelCase，SSOT = shared openapi schemas）；组装件从
``authn.state.registry()`` 取（Registry 单例缝，测试注 fake）。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

from django.http import HttpRequest

from authn.caches import map_saas_menus
from authn.config import AuthConfig
from authn.directory import CurrentUser, MyTenant
from authn.errors import (
    BadRequestError,
    InvalidCredentialsError,
    InvalidGrantError,
    MenusUnavailableError,
    NotFoundError,
    SaasIdpUnavailableError,
    SaasUpstreamError,
    UnauthorizedClientError,
)
from authn.jwt import require_bearer
from authn.saas_client import (
    SaasAvailableTenant,
    SaasCurrentUser,
    SaasLoginResponse,
    SaasPlatformTenant,
    SaasTenantMembership,
)
from authn.state import Registry, registry

log = logging.getLogger(__name__)

# 密码登录缺省 refresh token 载荷（AuthService.session "dev-placeholder" 镜像）
_DEV_PLACEHOLDER_REFRESH = "dev-placeholder"

# lab 家族在 saas 注册的 appCode（seeds apps.json 镜像）
_LAB_APP_CODE = "lab-management"

# msw 权限集（admin 全量 11 项，AuthService.DEMO_PERMISSIONS 镜像）
_DEMO_PERMISSIONS = [
    "contract:read",
    "contract:write",
    "sample:read",
    "sample:write",
    "report:read",
    "report:write",
    "report:issue",
    "inspection:read",
    "inspection:write",
    "audit:read",
    "*",
]


def _first_non_empty(*values: str | None) -> str:
    """空串 falsy 语义的首个非空值（saas user displayName 空串回退链——家族记忆
    saas-no-displayname-empty-string-fallback-trap）。"""
    for v in values:
        if v:
            return v
    return ""


def _user_dict(user: CurrentUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "displayName": user.display_name,
        "roleCode": user.role_code,
    }


def _tenant_dict(t: MyTenant) -> dict[str, Any]:
    return {"tenantId": t.tenant_id, "code": t.code, "name": t.name, "roleIds": list(t.role_ids)}


class AuthService:
    """M00.F01/F02 + M01.F04/F05（ADR-0008：配置式目录 + HS256 JWT + saas SSO）。"""

    def __init__(self, reg: Registry | None = None) -> None:
        self._external = reg

    @property
    def reg(self) -> Registry:
        return self._external if self._external is not None else registry()

    @property
    def config(self) -> AuthConfig:
        return self.reg.config

    # === M01.F05.I06 密码登录（AuthService.login 镜像） ===

    def login(self, username: str, password: str) -> dict[str, Any]:
        username = username.strip()
        if not username or not password:
            raise BadRequestError("username and password are required")
        # REQ-2026-023：账密校验代理 saas IdP。错误映射五仓统一：saas 4xx → 401
        # INVALID_CREDENTIALS（不透传）；5xx/不可达 → 502 SAAS_UNAVAILABLE。
        saas_login = self._proxy_saas_login(username, password)
        saas_user = saas_login.user
        # 租户名富化（best-effort，失败降级 name=tenantId）
        name_by_id = self._fetch_tenant_names(
            saas_login.user_id or (saas_user.id if saas_user is not None else ""),
            saas_login.access_token,
        )
        tenants = self._tenants_from_login(saas_login.available_tenants, name_by_id)
        user = CurrentUser(
            id=_first_non_empty(
                saas_user.id if saas_user is not None else None,
                saas_login.user_id,
                "unknown",
            ),
            username=_first_non_empty(
                saas_user.username if saas_user is not None else None,
                saas_user.email if saas_user is not None else None,
                "unknown",
            ),
            display_name=_first_non_empty(
                saas_user.display_name if saas_user is not None else None,
                saas_user.username if saas_user is not None else None,
                saas_user.email if saas_user is not None else None,
                "未知用户",
            ),
            role_code=(tenants[0].role_ids[0] if tenants and tenants[0].role_ids else "member"),
        )
        # 服务账号拉菜单快照（失败不阻塞登录，miss 时 menus 503）
        self._cache_menus_with_service_account(user.id)
        # 登录链落 membership 快照 + directory（me/switch 的 _resolve_user 按 sub 解析，
        # 不落目录必 unknown user 401）。5.120 家族裁定：upsert 首选 username。
        self.reg.membership_cache.put(user.id, tenants)
        self.reg.directory.upsert(
            user.id,
            _first_non_empty(user.username, saas_user.email if saas_user is not None else None),
            user.display_name,
            user.role_code,
        )
        # lab 自家 JWT 重签（tenant_id=saas currentTenantId ?? 首租户 → tenant_key）；
        # refresh 维持 dev-placeholder（不透传 saas refreshToken）
        return self._session(
            user,
            self._resolve_tenant_key(
                saas_login.current_tenant_id or (tenants[0].tenant_id if tenants else None),
                name_by_id,
            ),
            tenants,
            None,
        )

    def native_login(self, username: str, password: str) -> dict[str, Any]:
        # springboot AuthController native-login 直通 service.login（同源非浏览器通道）
        return self.login(username, password)

    # === M01.F05.I05 登出（无状态 JWT：服务端无 session store，204 由 view 收口） ===

    def logout(self) -> None:
        return None

    # === M00.F01.I01 当前会话（AuthService.me 镜像） ===

    def me(self, request: HttpRequest) -> dict[str, Any]:
        reg = self.reg
        claims = require_bearer(request, reg.jwt)
        user = self._resolve_user(claims)
        # 快照 hit 优先（SSO 与密码登录用户同链）；miss 且持 saas refresh（SSO 用户）→
        # refresh required 自愈；miss 且无 refresh（密码登录用户）→ demo 目录降级。
        cached_tenants = reg.membership_cache.get(user.id)
        if cached_tenants is not None:
            tenant_claim = claims.get("tenant_id")
            # 空快照回退 ""（空即空，禁 demo 兜底；终审 I2 家族级修复）
            current_tenant_id = (
                str(tenant_claim)
                if tenant_claim is not None
                else (cached_tenants[0].tenant_id if cached_tenants else "")
            )
            return {
                "user": _user_dict(user),
                "tenants": [_tenant_dict(t) for t in cached_tenants],
                "currentTenantId": current_tenant_id,
            }
        if reg.directory.get_saas_refresh_token(user.id):
            raise InvalidCredentialsError(
                f"membership snapshot unavailable for user {user.id} (cache miss); refresh required"
            )
        tenant_claim = claims.get("tenant_id")
        current_tenant_id = (
            str(tenant_claim)
            if tenant_claim is not None
            else reg.directory.default_tenant().tenant_id
        )
        return {
            "user": _user_dict(user),
            "tenants": [_tenant_dict(t) for t in reg.directory.tenants_of(user.username)],
            "currentTenantId": current_tenant_id,
        }

    # === M00.F02.I01 选租户换发（AuthService.switchTenant 镜像） ===

    def switch_tenant(self, request: HttpRequest, tenant_id: str) -> dict[str, Any]:
        reg = self.reg
        claims = require_bearer(request, reg.jwt)
        user = self._resolve_user(claims)
        # 归属=用户当前会话的租户集（membership 快照），demo 目录只作快照 miss 兜底。
        known_tenants = reg.membership_cache.get(user.id) or reg.directory.tenants_of(user.username)
        target = next((t for t in known_tenants if t.tenant_id == tenant_id), None)
        if target is None:
            raise NotFoundError("Tenant not found")
        return self._session(user, target.tenant_id, known_tenants, None)

    # === M01.F04.I01 动态菜单（miss 503，demo 兜底已删口径） ===

    def menus(self, request: HttpRequest) -> list[dict[str, Any]]:
        claims = require_bearer(request, self.reg.jwt)
        sub = claims.get("sub")
        sub_str = str(sub) if sub is not None else None
        snapshot = self.reg.menu_cache.get(sub_str)
        if snapshot is None:
            raise MenusUnavailableError(
                f"menu snapshot unavailable for user {sub_str}; re-login to refresh"
            )
        menus: list[dict[str, Any]] = snapshot  # 快照存取缝为 Any（fake 注入），出口收形
        return menus

    # === M01.F04.I02 权限集（admin 全量 11 项） ===

    def permissions(self, request: HttpRequest) -> dict[str, Any]:
        require_bearer(request, self.reg.jwt)
        return {"permissions": list(_DEMO_PERMISSIONS)}

    # === M01.F05.I04 刷新 token（AuthService.refresh 镜像） ===

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        if not refresh_token:
            raise InvalidCredentialsError("missing refresh_token")
        try:
            claims = self.reg.jwt.verify(refresh_token)
        except InvalidCredentialsError as exc:
            raise InvalidCredentialsError(f"invalid refresh_token: {exc.message}") from exc
        if claims.get("typ") != "refresh":
            raise InvalidCredentialsError("invalid refresh_token: not a refresh token")
        tenant_id = claims.get("tenant_id")
        saas_refresh = claims.get("saas_refresh_token")
        if not saas_refresh:
            raise InvalidCredentialsError("invalid refresh_token: missing saas_refresh_token claim")
        # 走 saas /oauth/token grantType=refresh_token；saas 失败包 401（前端触发重登）
        try:
            token = self.reg.saas_auth.token("refresh_token", None, str(saas_refresh), None)
        except (InvalidGrantError, UnauthorizedClientError, SaasUpstreamError) as exc:
            raise InvalidCredentialsError(f"saas refresh failed: {exc.message}") from exc
        saas_user = self.reg.saas_me.whoami(token.access_token)
        memberships = self.reg.saas_me.list_my_tenants(token.access_token)
        # 新部署/重启后 upserted 目录为空 → upsert 自愈（跟 ssoCallback 同款兜底）
        lab_user = self._upsert_by_email(saas_user)
        # rotate-once：新 saas refresh token 必须存回目录
        self.reg.directory.set_saas_refresh_token(lab_user.id, token.refresh_token)
        self._cache_menus(lab_user.id, token.access_token)
        name_by_id = self._fetch_tenant_names(lab_user.id, token.access_token)
        tenants = self._tenants_from(memberships, name_by_id)
        self.reg.membership_cache.put(lab_user.id, tenants)
        return self._session(
            lab_user, str(tenant_id) if tenant_id else None, tenants, token.refresh_token
        )

    # === M01.F05.I02 SSO 跳转（跳板形，家族收敛口径） ===

    def sso_authorize(self, redirect_uri: str | None, state: str | None) -> dict[str, Any]:
        cfg = self.config
        # 只消费 redirect_uri + state（response_type/client_id 参数被忽略——URL 里的
        # client_id 取 config 不取 query）。ADR-0019 + RFC 6749 §4.1.1：redirect_uri
        # 由前端发起，缺失 fail-fast 不兜 env。
        if redirect_uri is None or redirect_uri.strip() == "":
            raise BadRequestError("missing redirect_uri")
        state_value = state if state is not None else ""
        authorize_url = (
            f"{cfg.effective_login_url}/login"
            f"?redirect_uri={quote_plus(redirect_uri)}"
            f"&state={quote_plus(state_value)}"
            f"&client_id={quote_plus(cfg.saas_client_id)}"
        )
        return {"authorizeUrl": authorize_url, "state": state_value}

    # === M01.F05.I03 SSO 回调（AuthService.ssoCallback 镜像） ===

    def sso_callback(self, code: str, redirect_uri: str) -> dict[str, Any]:
        token = self.reg.saas_auth.token("authorization_code", code, None, redirect_uri)
        saas_user = self.reg.saas_me.whoami(token.access_token)
        memberships = self.reg.saas_me.list_my_tenants(token.access_token)
        lab_user = self._upsert_by_email(saas_user)
        # 菜单/成员资格快照：瞬时持有 saas accessToken 的窗口顺手拉齐；失败只 warn
        self._cache_menus(lab_user.id, token.access_token)
        self.reg.directory.set_saas_refresh_token(lab_user.id, token.refresh_token)
        name_by_id = self._fetch_tenant_names(lab_user.id, token.access_token)
        tenants = self._tenants_from(memberships, name_by_id)
        self.reg.membership_cache.put(lab_user.id, tenants)
        # token 带 tenant_id claim（whoami currentTenantId → tenant_key）
        return self._session(
            lab_user,
            self._resolve_tenant_key(saas_user.current_tenant_id, name_by_id),
            tenants,
            token.refresh_token,
        )

    # === 内部 helpers（AuthService 私有方法镜像） ===

    def _resolve_user(self, claims: dict[str, object]) -> CurrentUser:
        """sub claim 解析 lab 用户：id → email（SSO 写入路径）→ username（密码登录路径）。"""
        directory = self.reg.directory
        sub = claims.get("sub")
        sub_str = str(sub) if sub is not None else ""
        if not sub_str:
            raise InvalidCredentialsError("missing sub claim")
        user = (
            directory.find_by_id(sub_str)
            or directory.find_by_email(sub_str)
            or directory.find_by_username(sub_str)
        )
        if user is None:
            raise InvalidCredentialsError(f"unknown user: {sub_str}")
        return user

    def _upsert_by_email(self, saas_user: SaasCurrentUser) -> CurrentUser:
        # username → email 桥接（ADR-0008）；角色镜像 springboot 固定 "viewer"
        directory = self.reg.directory
        found = directory.find_by_email(saas_user.email)
        if found is not None:
            return found
        return directory.upsert(saas_user.id, saas_user.email, saas_user.display_name, "viewer")

    def _proxy_saas_login(self, username: str, password: str) -> SaasLoginResponse:
        """账密代理出站（REQ-2026-023）。错误归类：saas 4xx → 401（不透传 saas 内部码）；
        5xx/连接失败 → SaasIdpUnavailableError（502 SAAS_UNAVAILABLE）。"""
        try:
            login_response: SaasLoginResponse = self.reg.saas_auth.user_login(username, password)
            return login_response
        except (InvalidGrantError, UnauthorizedClientError) as exc:
            raise InvalidCredentialsError("Invalid username or password") from exc
        except SaasUpstreamError as exc:
            raise SaasIdpUnavailableError(f"saas IdP unavailable: {exc.message}") from exc

    def _tenants_from_login(
        self,
        available_tenants: list[SaasAvailableTenant],
        name_by_id: dict[str, SaasPlatformTenant],
    ) -> list[MyTenant]:
        """userLogin availableTenants → MyTenant：过滤无 tenantId/removed；命中富化
        tenantId=code=tenantKey（tenant_key 人裁）；miss 降级原值 tenantId。"""
        tenants: list[MyTenant] = []
        for t in available_tenants:
            if not t.tenant_id or t.status == "removed":
                continue
            n = name_by_id.get(t.tenant_id)
            tid = n.tenant_key if n is not None and n.tenant_key else t.tenant_id
            tenants.append(
                MyTenant(
                    tenant_id=tid,
                    code=tid,
                    name=n.name if n is not None and n.name else t.tenant_id,
                    role_ids=list(t.role_ids),
                )
            )
        return tenants

    def _cache_menus_with_service_account(self, user_id: str) -> None:
        """密码登录路径：服务账号登 saas 换 token 拉 /me/menus；失败只 warn。"""
        try:
            token = self.reg.saas_auth.service_login()
            self._cache_menus(user_id, token.access_token)
        except (InvalidGrantError, UnauthorizedClientError, SaasUpstreamError) as exc:
            log.warning(
                "service-account menu snapshot failed for user %s: %s", user_id, exc.message
            )

    def _cache_menus(self, user_id: str, saas_access_token: str) -> None:
        if not user_id or not saas_access_token:
            return
        try:
            snapshot = self.reg.saas_me.list_my_menus(saas_access_token, _LAB_APP_CODE)
            self.reg.menu_cache.put(user_id, map_saas_menus(snapshot))
        except (InvalidGrantError, UnauthorizedClientError, SaasUpstreamError) as exc:
            log.warning("menu snapshot fetch failed for user %s: %s", user_id, exc.message)

    def _fetch_tenant_names(
        self, user_id: str, saas_access_token: str
    ) -> dict[str, SaasPlatformTenant]:
        """租户显示名富化：memberships 只有 tenantId，趁瞬时 token 窗口拉平台租户列表
        填真名；失败降级 name=tenantId 只 warn。"""
        try:
            rows = self.reg.saas_me.list_platform_tenants(saas_access_token)
        except (InvalidGrantError, UnauthorizedClientError, SaasUpstreamError) as exc:
            log.warning("tenant name lookup failed for user %s: %s", user_id, exc.message)
            return {}
        return {t.id: t for t in rows if t.id}

    def _tenants_from(
        self,
        list_of_memberships: list[SaasTenantMembership],
        name_by_id: dict[str, SaasPlatformTenant],
    ) -> list[MyTenant]:
        """memberships → MyTenant：命中富化 tenantId=code=tenantKey/name；miss 降级原
        tenantId（切换器最差显示原标识，不空）。"""
        tenants: list[MyTenant] = []
        for m in list_of_memberships:
            t = name_by_id.get(m.tenant_id)
            tid = t.tenant_key if t is not None and t.tenant_key else m.tenant_id
            tenants.append(
                MyTenant(
                    tenant_id=tid,
                    code=tid,
                    name=t.name if t is not None and t.name else m.tenant_id,
                    role_ids=list(m.role_ids),
                )
            )
        return tenants

    @staticmethod
    def _resolve_tenant_key(
        saas_tenant_id: str | None, name_by_id: dict[str, SaasPlatformTenant]
    ) -> str | None:
        """tenant_key 人裁：对外交互用 key。命中且 tenantKey 非空 → tenantKey；
        miss/lookup 失败降级原标识。"""
        if not saas_tenant_id:
            return saas_tenant_id
        t = name_by_id.get(saas_tenant_id)
        return t.tenant_key if t is not None and t.tenant_key else saas_tenant_id

    def _session(
        self,
        user: CurrentUser,
        tenant_id: str | None,
        tenants: list[MyTenant] | None,
        saas_refresh_token: str | None,
    ) -> dict[str, Any]:
        access_token = self.reg.jwt.issue(user.id, tenant_id)
        refresh_token = self.reg.jwt.issue_refresh(
            user.id,
            saas_refresh_token if saas_refresh_token else _DEV_PLACEHOLDER_REFRESH,
        )
        use_tenants = (
            tenants if tenants is not None else self.reg.directory.tenants_of(user.username)
        )
        return {
            "token": access_token,
            "refreshToken": refresh_token,
            "user": _user_dict(user),
            "tenants": [_tenant_dict(t) for t in use_tenants],
        }
