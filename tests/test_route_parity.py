"""路由 parity（design-codegen.md）：django urls ⊇ manifest 切片 op（缺端点红），
wired ⊆ manifest 全量（私端点红）。manifest = scripts/gen-manifest.py 生成物（SSOT）。
lab 契约面无 /api/v1 前缀（CT contracts.test.ts PATH_LIST=/api/contracts）。"""

from __future__ import annotations

import json
from pathlib import Path

from django.urls import URLPattern, URLResolver

from config.urls import urlpatterns

MANIFEST = json.loads(
    (Path(__file__).resolve().parent.parent / "generated" / "api_manifest.json").read_text(
        encoding="utf-8"
    )
)

# 本切片（REQ-2026-030 contracts + T2 auth 域，REQ-2026-035）：契约路径 -> 功能子项
SLICE = {
    "GET /api/contracts": "M02.F01.I01",
    "POST /api/contracts": "M02.F01.I03",
    "GET /api/contracts/{id}": "M02.F01.I02",
    "PUT /api/contracts/{id}": "M02.F01.I04",
    "DELETE /api/contracts/{id}": "M02.F01.I05",
    # T2 auth 域 10 op（fastapi/springboot 同锚 ID）
    "GET /api/auth/me": "M00.F01.I01",
    "POST /api/auth/login": "M01.F05.I01",
    "POST /api/auth/native-login": "M01.F05.I01",
    "POST /api/auth/logout": "M01.F05.I05",
    "POST /api/auth/refresh": "M01.F05.I04",
    "GET /api/auth/menus": "M01.F04.I01",
    "GET /api/auth/permissions": "M01.F04.I02",
    "POST /api/auth/switch-tenant": "M00.F02.I01",
    "GET /api/auth/sso/authorize": "M01.F05.I02",
    "POST /api/auth/sso/callback": "M01.F05.I03",
}


def _walk(patterns: list, prefix: str = ""):
    for p in patterns:
        if isinstance(p, URLPattern):
            yield prefix + str(p.pattern)
        elif isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))


def _normalize(route: str) -> str:
    return ("/" + route).replace("<str:contract_id>", "{id}").rstrip("/")


def _wired() -> set[str]:
    return {_normalize(r) for r in _walk(urlpatterns) if r}


def test_manifest_has_slice_ops() -> None:
    ops = {f"{o['method']} {o['path']}" for o in MANIFEST["operations"]}
    missing = SLICE.keys() - ops
    assert not missing, f"契约 manifest 缺切片 op: {missing}"


def test_slice_ops_all_wired() -> None:
    wired = _wired()
    for op, fid in SLICE.items():
        path = op.split(" ", 1)[1]
        assert path in wired, f"{fid} {op} 未按契约挂载"


def test_no_undocumented_routes() -> None:
    manifest_paths = {o["path"] for o in MANIFEST["operations"]}
    extra = _wired() - manifest_paths
    assert not extra, f"未在契约 manifest 的私端点: {extra}"
