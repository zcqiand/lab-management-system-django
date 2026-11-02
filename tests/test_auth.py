"""auth 域 10 op 单测（T2，REQ-2026-035；语义正源 = lab-fastapi impl/auth_impl.py，
其注释标注逐条对照 lab-springboot AuthService.java——本仓镜像同语义）。

- fake saas client 注入 ``authn.state.registry`` 缝（家族 REQ §6：SSO/登录簇以契约
  形状锁为主，saas 真连归 T11 contract-test live）；
- 认证域无 DB（内存目录 ConfigUserDirectory，家族 dev 约定）；
- env 全走 .env.test（fail-fast 无兜底，suite-hard-rules §1）。
"""

from __future__ import annotations

import os
from typing import Any

import jwt as pyjwt
import pytest
from rest_framework.test import APIClient

from authn import state as authn_state
from authn.errors import (
    ApiError,
    InvalidGrantError,
    SaasUpstreamError,
    UnauthorizedClientError,
)
from authn.saas_client import (
    SaasAuthClient,
    SaasCurrentUser,
    SaasLoginResponse,
    SaasMenuNode,
    SaasPlatformTenant,
    SaasTenantMembership,
    TokenResponse,
)
from authn.state import Registry

TEST_KEY = os.environ["JWT_SIGNING_KEY"]
ISSUER = os.environ["JWT_ISSUER"]


class FakeSaasAuth:
    """saas /api/v1/auth/login + /api/v1/oauth/token 替身（形状对齐 SaasAuthClient）。

    user_login demo 形：alice→USER-A、三 demo 租户；user_login_failure 注错走
    saas 4xx → 401 映射路径；token rotate-once（递增 refresh，消费即轮换可观测）。
    """

    def __init__(self) -> None:
        self.token_calls: list[dict[str, str | None]] = []
        self.user_login_failure: Exception | None = None
        self._n = 0

    def user_login(self, username: str, _password: str) -> SaasLoginResponse:
        if self.user_login_failure is not None:
            raise self.user_login_failure
        return SaasLoginResponse.model_validate(
            {
                "user": {
                    "id": "USER-A",
                    "username": username,
                    "email": "alice@saas.local",
                    "displayName": "管理员",
                },
                "availableTenants": [
                    {"tenantId": "TENANT-001", "roleIds": ["admin"], "status": "active"},
                    {"tenantId": "TENANT-002", "roleIds": ["technician"], "status": "active"},
                    {"tenantId": "TENANT-003", "roleIds": ["viewer"], "status": "active"},
                ],
                "accessToken": "user-access-token",
                "refreshToken": "user-refresh-token",
                "userId": "USER-A",
            }
        )

    def service_login(self) -> TokenResponse:
        return TokenResponse(access_token="svc-access", refresh_token="svc-refresh")

    def token(
        self,
        grant_type: str,
        code: str | None = None,
        refresh_token: str | None = None,
        redirect_uri: str | None = None,
    ) -> TokenResponse:
        self.token_calls.append(
            {
                "grant_type": grant_type,
                "code": code,
                "refresh_token": refresh_token,
                "redirect_uri": redirect_uri,
            }
        )
        if refresh_token == "expired-saas-refresh":
            raise InvalidGrantError('saas 400 {"error":"invalid_grant"}')
        self._n += 1
        return TokenResponse(
            access_token=f"saas-access-{self._n}", refresh_token=f"saas-refresh-{self._n}"
        )


class FakeSaasMe:
    """saas /api/v1/me* 替身：bob@lab.dev 在 saas 侧隶属 T-9（technician）。"""

    def whoami(self, _access_token: str) -> SaasCurrentUser:
        return SaasCurrentUser(
            id="saas-user-1",
            email="bob@lab.dev",
            displayName="Bob",
            currentTenantId="T-9",
        )

    def list_my_tenants(self, _access_token: str) -> list[SaasTenantMembership]:
        return [SaasTenantMembership(tenantId="T-9", roleIds=["technician"])]

    def list_my_menus(self, _access_token: str, app_code: str) -> list[SaasMenuNode]:
        if app_code != "lab-management":
            return []
        return [
            SaasMenuNode(id="m2", code="audit", type="page", sortOrder=1),
            SaasMenuNode(
                id="m1",
                code="inspection",
                title="试验过程",
                type="group",
                sortOrder=2,
                children=[
                    SaasMenuNode(
                        id="m1-1", code="samples", title="接样管理", type="page", sortOrder=2
                    ),
                    SaasMenuNode(
                        id="m1-2", code="records", title="数据录入", type="page", sortOrder=1
                    ),
                ],
            ),
        ]

    def list_platform_tenants(self, _access_token: str) -> list[SaasPlatformTenant]:
        return [
            SaasPlatformTenant(id="T-9", name="第三方平台租户", tenantKey="t9"),
            SaasPlatformTenant(
                id="TENANT-001", name="市住建工程质量检测中心", tenantKey="city-lab"
            ),
        ]


@pytest.fixture()
def reg() -> Any:
    r = Registry.from_env()
    r.saas_auth = FakeSaasAuth()
    r.saas_me = FakeSaasMe()
    authn_state.set_registry(r)
    yield r
    authn_state.set_registry(None)


@pytest.fixture()
def client(reg: Any) -> APIClient:  # noqa: ARG001 reg 侧效应挂缝
    return APIClient()


def login(client: APIClient, username: str = "alice", password: str = "dev123456") -> dict:
    resp = client.post(
        "/api/auth/login", {"username": username, "password": password}, format="json"
    )
    assert resp.status_code == 200, resp.content
    return resp.json()


def decode(token: str) -> dict:
    """lab JWT 无 aud（verify_aud=False 镜像家族五仓 verify 只验 sig/iss/exp）。"""
    return pyjwt.decode(
        token, TEST_KEY, algorithms=["HS256"], issuer=ISSUER, options={"verify_aud": False}
    )


def sso_login(client: APIClient) -> dict:
    resp = client.post(
        "/api/auth/sso/callback",
        {
            "grant_type": "authorization_code",
            "code": "one-time-code",
            "redirect_uri": "http://localhost:5213/login",
            "state": "s1",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.json()


# === M01.F05.I01 密码登录（+ native-login 同源直通） ===


@pytest.mark.fn("M01.F05.I01")
def test_login_ok(client: APIClient) -> None:
    body = login(client)
    assert body["user"] == {
        "id": "USER-A",
        "username": "alice",
        "displayName": "管理员",
        "roleCode": "admin",
    }
    # 2026-10-20 租户标识=tenant_key：命中租户 tenantId=city-lab；miss 降级原 tenantId
    assert {t["tenantId"] for t in body["tenants"]} == {"city-lab", "TENANT-002", "TENANT-003"}
    assert body["tenants"][0] == {
        "tenantId": "city-lab",
        "code": "city-lab",
        "name": "市住建工程质量检测中心",
        "roleIds": ["admin"],
    }
    access = decode(body["token"])
    assert access["typ"] == "access" and access["sub"] == "USER-A"
    assert access["tenant_id"] == "city-lab"
    refresh = decode(body["refreshToken"])
    assert refresh["typ"] == "refresh" and refresh["saas_refresh_token"] == "dev-placeholder"


@pytest.mark.fn("M01.F05.I01")
def test_login_native_same_path(client: APIClient) -> None:
    resp = client.post(
        "/api/auth/native-login", {"username": "alice", "password": "dev123456"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == "USER-A"


@pytest.mark.fn("M01.F05.I01")
def test_login_bad_password_401(client: APIClient, reg: Any) -> None:
    fake: FakeSaasAuth = reg.saas_auth
    fake.user_login_failure = InvalidGrantError('saas 400 {"error":"invalid_grant"}')
    resp = client.post("/api/auth/login", {"username": "alice", "password": "wrong"}, format="json")
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.fn("M01.F05.I01")
def test_login_missing_field_400(client: APIClient) -> None:
    resp = client.post("/api/auth/login", {"username": "alice"}, format="json")
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"


# === M01.F05.I05 登出（无状态 204） ===


@pytest.mark.fn("M01.F05.I05")
def test_logout_204(client: APIClient) -> None:
    resp = client.post("/api/auth/logout", {"token": "whatever"}, format="json")
    assert resp.status_code == 204
    assert resp.content == b""


# === M00.F01.I01 当前会话 ===


@pytest.mark.fn("M00.F01.I01")
def test_me_password_user(client: APIClient) -> None:
    token = login(client)["token"]
    resp = client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == "USER-A"
    assert len(body["tenants"]) == 3
    assert body["currentTenantId"] == "city-lab"


@pytest.mark.fn("M00.F01.I01")
def test_me_requires_bearer(client: APIClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    resp = client.get("/api/auth/me", HTTP_AUTHORIZATION="Bearer not-a-jwt")
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.fn("M00.F01.I01")
def test_me_sso_user_reads_membership_cache(client: APIClient) -> None:
    body = sso_login(client)
    resp = client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {body['token']}")
    assert resp.status_code == 200
    me = resp.json()
    # SSO 用户走 saas memberships 体系；tenantId/currentTenantId=tenantKey（t9）
    assert me["tenants"] == [
        {"tenantId": "t9", "code": "t9", "name": "第三方平台租户", "roleIds": ["technician"]}
    ]
    assert me["currentTenantId"] == "t9"


@pytest.mark.fn("M00.F01.I01")
def test_me_sso_user_cache_miss_401(client: APIClient, reg: Any) -> None:
    body = sso_login(client)
    reg.membership_cache._snapshots.clear()  # type: ignore[attr-defined]  # noqa: SLF001 测试缝
    resp = client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {body['token']}")
    assert resp.status_code == 401
    assert "refresh required" in resp.json()["message"]


# === M00.F02.I01 选租户换发 ===


@pytest.mark.fn("M00.F02.I01")
def test_switch_tenant_reissues_token_with_claim(client: APIClient) -> None:
    token = login(client)["token"]
    resp = client.post(
        "/api/auth/switch-tenant",
        {"tenantId": "TENANT-002"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert decode(body["token"])["tenant_id"] == "TENANT-002"
    assert len(body["tenants"]) == 3  # 租户列表全量回显


@pytest.mark.fn("M00.F02.I01")
def test_switch_unknown_tenant_404(client: APIClient) -> None:
    token = login(client)["token"]
    resp = client.post(
        "/api/auth/switch-tenant",
        {"tenantId": "TENANT-404"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# === M01.F04.I01 动态菜单 / I02 权限集 ===


@pytest.mark.fn("M01.F04.I01")
def test_menus_from_snapshot(client: APIClient, reg: Any) -> None:
    login(client)  # 密码登录触发服务账号菜单快照
    token = reg.jwt.issue("USER-A", None)
    resp = client.get("/api/auth/menus", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200
    tree = resp.json()
    assert [n["id"] for n in tree] == ["m2", "m1"]  # sortOrder 升序
    assert tree[0]["label"] == "audit"  # title 缺省回落 code
    assert tree[0]["icon"] == "file"  # page 缺省 icon
    group = tree[1]
    assert group["label"] == "试验过程" and group["icon"] == "resource"
    assert [c["id"] for c in group["children"]] == ["m1-2", "m1-1"]


@pytest.mark.fn("M01.F04.I01")
def test_menus_miss_503(client: APIClient, reg: Any) -> None:
    login(client)
    reg.menu_cache._snapshots.clear()  # type: ignore[attr-defined]  # noqa: SLF001 测试缝
    token = reg.jwt.issue("USER-A", None)
    resp = client.get("/api/auth/menus", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 503
    assert resp.json()["code"] == "MENUS_UNAVAILABLE"


@pytest.mark.fn("M01.F04.I02")
def test_permissions_admin_11(client: APIClient) -> None:
    token = login(client)["token"]
    resp = client.get("/api/auth/permissions", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200
    assert resp.json()["permissions"] == [
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


# === M01.F05.I04 刷新 token ===


@pytest.mark.fn("M01.F05.I04")
def test_refresh_via_saas_rotation(client: APIClient, reg: Any) -> None:
    body = sso_login(client)  # SSO 用户的 refresh token 内嵌真 saas refresh
    fake: FakeSaasAuth = reg.saas_auth
    resp = client.post("/api/auth/refresh", {"refreshToken": body["refreshToken"]}, format="json")
    assert resp.status_code == 200, resp.content
    assert fake.token_calls[-1] == {
        "grant_type": "refresh_token",
        "code": None,
        "refresh_token": "saas-refresh-1",  # sso 回调存回的旧 saas refresh
        "redirect_uri": None,
    }
    new = resp.json()
    assert decode(new["refreshToken"])["saas_refresh_token"] == "saas-refresh-2"
    # rotate-once：新 saas refresh 必须存回目录
    assert reg.directory.get_saas_refresh_token("saas-user-1") == "saas-refresh-2"
    assert [t["tenantId"] for t in new["tenants"]] == ["t9"]


@pytest.mark.fn("M01.F05.I04")
def test_refresh_saas_reject_401(client: APIClient, reg: Any) -> None:
    bad = reg.jwt.issue_refresh("USER-A", "expired-saas-refresh")
    resp = client.post("/api/auth/refresh", {"refreshToken": bad}, format="json")
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.fn("M01.F05.I04")
def test_refresh_rejects_access_token(client: APIClient) -> None:
    token = login(client)["token"]
    resp = client.post("/api/auth/refresh", {"refreshToken": token}, format="json")
    assert resp.status_code == 401  # typ=access 不是 refresh token


# === M01.F05.I02 SSO 跳转（跳板形） ===


@pytest.mark.fn("M01.F05.I02")
def test_sso_authorize_jump_board_shape(client: APIClient) -> None:
    resp = client.get(
        "/api/auth/sso/authorize",
        {
            "response_type": "code",
            "client_id": "from-query-ignored",
            "redirect_uri": "http://localhost:5213/login",
            "state": "csrf-123",
        },
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["state"] == "csrf-123"
    expected_base = os.environ["LAB_SSO_LOGIN_URL"] or os.environ["LAB_SAAS_BASE_URL"]
    assert body["authorizeUrl"] == (
        f"{expected_base}/login"
        "?redirect_uri=http%3A%2F%2Flocalhost%3A5213%2Flogin"
        "&state=csrf-123&client_id=lab-management"
    )
    assert "from-query-ignored" not in body["authorizeUrl"]


@pytest.mark.fn("M01.F05.I02")
def test_sso_authorize_missing_redirect_400(client: APIClient) -> None:
    resp = client.get("/api/auth/sso/authorize", {"state": "csrf-123"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"


# === M01.F05.I03 SSO 回调（code 换 token + email upsert + 双快照） ===


@pytest.mark.fn("M01.F05.I03")
def test_sso_callback_full_flow(client: APIClient) -> None:
    body = sso_login(client)
    assert body["user"] == {
        "id": "saas-user-1",
        "username": "bob@lab.dev",  # upsert username=email（ADR-0008 桥接）
        "displayName": "Bob",
        "roleCode": "viewer",
    }
    assert decode(body["token"])["tenant_id"] == "t9"
    assert decode(body["refreshToken"])["saas_refresh_token"] == "saas-refresh-1"
    assert [t["name"] for t in body["tenants"]] == ["第三方平台租户"]
    resp = client.get("/api/auth/menus", HTTP_AUTHORIZATION=f"Bearer {body['token']}")
    assert resp.status_code == 200  # 菜单快照已进缓存


@pytest.mark.fn("M01.F05.I03")
def test_sso_callback_second_login_upserts_once(client: APIClient, reg: Any) -> None:
    first = sso_login(client)
    second = sso_login(client)
    assert first["user"]["id"] == second["user"]["id"]
    assert len(reg.directory._upserted) == 1  # type: ignore[attr-defined]  # noqa: SLF001 测试缝


# === REQ-2026-023 登录代理语义（test_auth_login_proxy 移植） ===


class RecordingSaasAuth(FakeSaasAuth):
    """记录出站账密的替身（demo 形 TEN-1/TEN-2，刻意非 demo 三租户）。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str]] = []

    def user_login(self, username: str, password: str) -> SaasLoginResponse:
        self.calls.append((username, password))
        if self.user_login_failure is not None:
            raise self.user_login_failure
        return SaasLoginResponse.model_validate(
            {
                "user": {"id": "saas-user-alice", "username": "alice", "email": "alice@saas.local"},
                "availableTenants": [
                    {"tenantId": "TEN-1", "roleIds": ["admin"], "status": "active"},
                    {"tenantId": "TEN-2", "roleIds": ["technician"], "status": "active"},
                ],
                "accessToken": "u-at",
                "refreshToken": "u-rt",
                "userId": "saas-user-alice",
            }
        )


class EnrichingSaasMe(FakeSaasMe):
    """平台租户只富化 TEN-1（TEN-2 不在列表 → 降级路径）；菜单树恒空。"""

    def list_platform_tenants(self, _access_token: str) -> list[SaasPlatformTenant]:
        return [SaasPlatformTenant(id="TEN-1", name="市检测中心", tenantKey="city")]

    def list_my_menus(self, _access_token: str, _app_code: str) -> list[SaasMenuNode]:
        return []


@pytest.mark.fn("M01.F05.I01")
def test_login_proxies_saas_and_resigns_lab_jwt(client: APIClient, reg: Any) -> None:
    reg.saas_auth = RecordingSaasAuth()
    reg.saas_me = EnrichingSaasMe()
    resp = client.post(
        "/api/auth/login", {"username": "alice", "password": "pw-123"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert reg.saas_auth.calls == [("alice", "pw-123")]  # type: ignore[attr-defined]
    assert body["user"] == {
        "id": "saas-user-alice",
        "username": "alice",
        "displayName": "alice",
        "roleCode": "admin",
    }
    assert body["tenants"] == [
        {"tenantId": "city", "code": "city", "name": "市检测中心", "roleIds": ["admin"]},
        {"tenantId": "TEN-2", "code": "TEN-2", "name": "TEN-2", "roleIds": ["technician"]},
    ]
    access = decode(body["token"])
    assert access["sub"] == "saas-user-alice"
    assert access["tenant_id"] == "city"
    refresh = decode(body["refreshToken"])
    assert refresh["saas_refresh_token"] == "dev-placeholder"


UUID_USER = "00000000-0000-0000-0000-b00000000001"


class UuidSaasAuth(RecordingSaasAuth):
    """live 回归替身：saas 真实租户 UUID 形（刻意不用 demo 形撞键掩盖失配）。"""

    def user_login(self, username: str, password: str) -> SaasLoginResponse:
        self.calls.append((username, password))
        return SaasLoginResponse.model_validate(
            {
                "user": {"id": UUID_USER, "username": "alice", "email": "alice@saas.local"},
                "availableTenants": [
                    {
                        "tenantId": "00000000-0000-0000-0000-000000000001",
                        "roleIds": ["admin"],
                        "status": "active",
                    },
                    {
                        "tenantId": "00000000-0000-0000-0000-000000000002",
                        "roleIds": ["technician"],
                        "status": "active",
                    },
                ],
                "accessToken": "u-at",
                "refreshToken": "u-rt",
                "userId": UUID_USER,
            }
        )


@pytest.mark.fn("M00.F01.I01", "M00.F02.I01")
def test_login_session_coherence_me_and_switch_stay_in_saas_tenant_system(
    client: APIClient, reg: Any
) -> None:
    reg.saas_auth = UuidSaasAuth()
    resp = client.post(
        "/api/auth/login", {"username": "alice", "password": "pw-123"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    tid = body["tenants"][0]["tenantId"]
    assert tid == "00000000-0000-0000-0000-000000000001"
    bearer = {"HTTP_AUTHORIZATION": f"Bearer {body['token']}"}

    me = client.get("/api/auth/me", **bearer)
    assert me.status_code == 200, me.content
    me_body = me.json()
    assert me_body["tenants"][0]["tenantId"] == tid
    assert len(me_body["tenants"]) == len(body["tenants"])
    assert me_body["user"]["username"] == body["user"]["username"]

    switched = client.post("/api/auth/switch-tenant", {"tenantId": tid}, format="json", **bearer)
    assert switched.status_code == 200, switched.content
    switched_body = switched.json()
    assert len(switched_body["token"].split(".")) == 3
    assert decode(switched_body["token"])["tenant_id"] == tid


@pytest.mark.fn("M01.F05.I01")
def test_saas_client_user_login_sends_oauth_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """出站 body clientId=OAuth client id（LAB_SAAS_CLIENT_ID），不是 service_client_id。"""
    captured: dict[str, Any] = {}

    class FakeResp:
        status_code = 200
        text = "{}"

        def json(self) -> dict:
            return {
                "user": {"id": "u1", "username": "alice"},
                "availableTenants": [],
                "accessToken": "at",
            }

    def fake_request(_method: str, url: str, json: dict | None = None, **_kw: object) -> FakeResp:
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr("authn.saas_client.httpx.request", fake_request)
    resp = SaasAuthClient().user_login("alice", "pw-123")
    assert str(captured["url"]).endswith("/api/v1/auth/login")
    assert captured["json"] == {
        "username": "alice",
        "password": "pw-123",
        "clientId": os.environ["LAB_SAAS_CLIENT_ID"],
    }
    assert resp.user is not None and resp.user.username == "alice"


class ZeroTenantSaasAuth(RecordingSaasAuth):
    """零 active 租户用户：快照空列表 + token 无 tenant_id claim。"""

    def user_login(self, username: str, password: str) -> SaasLoginResponse:
        self.calls.append((username, password))
        return SaasLoginResponse.model_validate(
            {
                "user": {"id": "saas-user-oscar", "username": "oscar", "email": "oscar@saas.local"},
                "availableTenants": [],
                "accessToken": "u-at",
                "refreshToken": "u-rt",
                "userId": "saas-user-oscar",
            }
        )


@pytest.mark.fn("M00.F01.I01")
def test_me_empty_membership_snapshot_is_empty_current_tenant_not_500(
    client: APIClient, reg: Any
) -> None:
    # 空即空（tenants=[] + currentTenantId=""，禁 demo 兜底），非 IndexError → 500
    reg.saas_auth = ZeroTenantSaasAuth()
    login_resp = client.post(
        "/api/auth/login", {"username": "oscar", "password": "pw"}, format="json"
    )
    assert login_resp.status_code == 200, login_resp.content
    token = login_resp.json()["token"]
    resp = client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["tenants"] == []
    assert body["currentTenantId"] == ""


# saas 4xx 细分：401→UnauthorizedClientError（401 INVALID_CREDENTIALS）、其他 4xx→
# InvalidGrantError（400 INVALID_GRANT）——错误分流单测（saas_client._raise_for_saas_status）


def test_saas_status_mapping() -> None:
    from authn.saas_client import _raise_for_saas_status  # noqa: PLC0415 测试探内件

    with pytest.raises(UnauthorizedClientError):
        _raise_for_saas_status(401, "body", "auth/login")
    with pytest.raises(InvalidGrantError):
        _raise_for_saas_status(400, "body", "auth/login")
    with pytest.raises(SaasUpstreamError):
        _raise_for_saas_status(500, "body", "auth/login")
    assert issubclass(ApiError, Exception)
