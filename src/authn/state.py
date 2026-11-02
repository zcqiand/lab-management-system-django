"""authn 域运行时组合根 —— Registry（依赖集）+ 进程级单例缝。

fastapi 组合根走 app.state；Django 无 app 对象可挂（wsgi 多进程），用模块级单例：
首次 ``registry()`` 惰性自 env 组装，测试以 ``set_registry`` 注 fake（家族 REQ §6
saas 缝不真连）。重启即清（内存目录/快照缓存家族语义）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from authn.caches import MembershipSnapshotCache, MenuSnapshotCache
from authn.config import AuthConfig
from authn.directory import ConfigUserDirectory
from authn.jwt import JwtIssuer
from authn.saas_client import SaasAuthClient, SaasMeClient


@dataclass
class Registry:
    config: AuthConfig
    jwt: JwtIssuer
    directory: ConfigUserDirectory
    saas_auth: Any  # SaasAuthClient | fake（测试注缝，家族同 fastapi app.state 形）
    saas_me: Any  # SaasMeClient | fake
    menu_cache: MenuSnapshotCache = field(default_factory=MenuSnapshotCache)
    membership_cache: MembershipSnapshotCache = field(default_factory=MembershipSnapshotCache)

    @classmethod
    def from_env(cls) -> Registry:
        config = AuthConfig.from_env()
        return cls(
            config=config,
            jwt=JwtIssuer(config),
            directory=ConfigUserDirectory(),
            saas_auth=SaasAuthClient(config),
            saas_me=SaasMeClient(config.saas_base_url),
        )


_registry: Registry | None = None


def registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry.from_env()
    return _registry


def set_registry(value: Registry | None) -> None:
    """测试缝：注入替身 registry / None 复位（下个请求重新惰性组装）。"""
    global _registry
    _registry = value
