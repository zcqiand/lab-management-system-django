"""配置式内存用户目录 —— lab-springboot ConfigUserDirectory 1:1 镜像（fastapi
impl/directory.py 同源）。

数据 1:1 镜像 lab-msw（家族 dev 约定）：

- 用户：alice（USER-A，roleCode=admin）——REQ-2026-023：口令校验已代理 saas IdP，
  本目录只承担 SSO/refresh/me 的用户与租户查找
- 租户：TENANT-001 city-lab / TENANT-002 district-lab / TENANT-003 third-party
- 运行时 upsert：SSO 用户按 email 键落 ``_upserted`` 内存 Map（重启即清，refresh 自愈链兜底）
- per-user saas refresh_token：saas rotate-once 消费即作废，me/menus 缓存 miss
  reload 后必须存回新的
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CurrentUser:
    # 内部 snake_case；契约 camelCase 键在 service._user_dict/_tenant_dict 映射
    # （字段名不直接对契约——N815 mixedCase 豁免比改名更脏）
    id: str
    username: str
    display_name: str
    role_code: str


@dataclass
class MyTenant:
    tenant_id: str
    code: str
    name: str
    role_ids: list[str]


_DEMO_USER = CurrentUser(id="USER-A", username="alice", display_name="管理员", role_code="admin")

_TENANTS: list[MyTenant] = [
    MyTenant(
        tenant_id="TENANT-001", code="city-lab", name="市住建工程质量检测中心", role_ids=["admin"]
    ),
    MyTenant(tenant_id="TENANT-002", code="district-lab", name="区检测站", role_ids=["technician"]),
    MyTenant(
        tenant_id="TENANT-003", code="third-party", name="第三方检测实验室", role_ids=["viewer"]
    ),
]


class ConfigUserDirectory:
    """无身份表的配置式目录（ADR-0008）：查/比/upsert 全内存。"""

    def __init__(self) -> None:
        self._upserted: dict[str, CurrentUser] = {}
        self._saas_refresh_tokens: dict[str, str] = {}

    def find_by_username(self, username: str | None) -> CurrentUser | None:
        if username is None:
            return None
        if _DEMO_USER.username == username:
            return _DEMO_USER
        return next((u for u in self._upserted.values() if u.username == username), None)

    def find_by_email(self, email: str | None) -> CurrentUser | None:
        # 镜像 quirk：springboot findByEmail 对 DEMO 用户比对的是 username（非 email 字段）
        if email is None:
            return None
        if email == _DEMO_USER.username:
            return _DEMO_USER
        return next((u for u in self._upserted.values() if u.username == email), None)

    def find_by_id(self, user_id: str | None) -> CurrentUser | None:
        if user_id is None:
            return None
        if _DEMO_USER.id == user_id:
            return _DEMO_USER
        return next((u for u in self._upserted.values() if u.id == user_id), None)

    def tenants_of(self, _username: str) -> list[MyTenant]:
        # 镜像 springboot UserDirectory 接口形参：demo 目录全体用户租户一致
        return list(_TENANTS)

    def default_tenant(self) -> MyTenant:
        return _TENANTS[0]

    def upsert(
        self, user_id: str, email: str, display_name: str | None, role_code: str | None
    ) -> CurrentUser:
        # 优先按 email 找，命中即返回既有（不更新字段，镜像 springboot）；roleCode 空兜 viewer
        existing = self._upserted.get(email)
        if existing is not None:
            return existing
        user = CurrentUser(
            id=user_id,
            username=email,
            display_name=display_name if display_name else "",
            role_code=role_code if role_code else "viewer",
        )
        self._upserted[email] = user
        return user

    def set_saas_refresh_token(self, user_id: str | None, saas_refresh_token: str | None) -> None:
        if not user_id or not saas_refresh_token:
            return
        self._saas_refresh_tokens[user_id] = saas_refresh_token

    def get_saas_refresh_token(self, user_id: str) -> str | None:
        if not user_id:
            return None
        return self._saas_refresh_tokens.get(user_id)
