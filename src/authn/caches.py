"""菜单/成员资格快照缓存 + saas 菜单树映射 —— lab-springboot MenuSnapshotCache /
MembershipSnapshotCache / SaasMenuMapper 镜像（fastapi impl/menu_cache.py 同源）。

局限同 springboot（javadoc）：进程内缓存多实例不共享；TTL 30min 后需 refresh 或
重登重新填充。菜单变更生效时延 = min(refresh 周期, TTL)。
"""

from __future__ import annotations

import datetime
from typing import Any

from authn.saas_client import SaasMenuNode

_TTL = datetime.timedelta(minutes=30)

# group 类型节点缺省 icon（SaasMenuMapper 常量镜像）
DEFAULT_GROUP_ICON = "resource"
DEFAULT_PAGE_ICON = "file"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _sorted_by_sort_order(nodes: list[SaasMenuNode]) -> list[SaasMenuNode]:
    """sortOrder 升序、None 置尾（nullsLast 镜像）。"""
    return sorted(nodes, key=lambda n: (n.sort_order is None, n.sort_order or 0))


def map_saas_menus(roots: list[SaasMenuNode]) -> list[dict[str, Any]]:
    """saas EffectiveMenuNode → lab 契约 MenuNode 递归映射。

    label = title ?? code（saas 名称字段是 title）；icon = icon ?? (group→"resource"、
    page→"file")；子树防御性再排一次。children 空落 null（pydantic None 镜像）。
    """
    return [_map_node(node) for node in _sorted_by_sort_order(roots)]


def _map_node(src: SaasMenuNode) -> dict[str, Any]:
    icon = src.icon
    if not icon:
        icon = DEFAULT_GROUP_ICON if src.type == "group" else DEFAULT_PAGE_ICON
    children = [_map_node(child) for child in _sorted_by_sort_order(src.children)]
    return {
        "id": src.id,
        "label": src.title if src.title else src.code if src.code else src.id,
        "path": src.path,
        "icon": icon,
        "children": children or None,
    }


class _SnapshotCache:
    """per-user 快照基座（TTL 过期即逐出）。"""

    def __init__(self, ttl: datetime.timedelta = _TTL) -> None:
        self._ttl = ttl
        self._snapshots: dict[str, tuple[Any, datetime.datetime]] = {}

    def put(self, user_id: str, value: Any) -> None:
        self._snapshots[user_id] = (value, _now() + self._ttl)

    def get(self, user_id: str | None) -> Any | None:
        if user_id is None:
            return None
        entry = self._snapshots.get(user_id)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at < _now():
            del self._snapshots[user_id]
            return None
        return value


class MenuSnapshotCache(_SnapshotCache):
    """per-user 已映射菜单树快照（miss → /menus 503 MENUS_UNAVAILABLE，demo 兜底已删口径）。"""


class MembershipSnapshotCache(_SnapshotCache):
    """per-user saas memberships 快照（me() 对 SSO 用户必读；miss → 401 refresh 自愈）。"""
