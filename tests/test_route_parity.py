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
    "POST /api/auth/login": "M01.F05.I06",
    "POST /api/auth/native-login": "M01.F05.I06",
    "POST /api/auth/logout": "M01.F05.I05",
    "POST /api/auth/refresh": "M01.F05.I04",
    "GET /api/auth/menus": "M01.F04.I01",
    "GET /api/auth/permissions": "M01.F04.I02",
    "POST /api/auth/switch-tenant": "M00.F02.I01",
    "GET /api/auth/sso/authorize": "M01.F05.I02",
    "POST /api/auth/sso/callback": "M01.F05.I03",
    # T5 接样单域 14 op（CRUD 5 + history + task + 七段 act；rails 同款 stage 映射）
    "GET /api/receipts": "M03.F01.I01",
    "POST /api/receipts": "M03.F01.I03",
    "GET /api/receipts/{id}": "M03.F01.I02",
    "PUT /api/receipts/{id}": "M03.F01.I04",
    "DELETE /api/receipts/{id}": "M03.F01.I05",
    "GET /api/receipts/{id}/history": "M03.F01.I06",
    "PUT /api/receipts/{id}/task": "M03.F02.I01",
    "POST /api/receipts/receiving/act": "M03.F01.I08",
    "POST /api/receipts/assigning/act": "M03.F02.I05",
    "POST /api/receipts/data-entry/act": "M03.F03.I12",
    "POST /api/receipts/review/act": "M03.F05.I07",
    "POST /api/receipts/approve/act": "M03.F06.I05",
    "POST /api/receipts/issuance/act": "M03.F07.I05",
    "POST /api/receipts/archived/act": "M03.F08.I05",
    # T6 样品 + 检测记录域 12 op（ext 补录锚 M03.F01.I07；verdict PATCH 见 .tsp 2026-09-18 修正）
    "GET /api/samples": "M03.F03.I01",
    "POST /api/samples": "M03.F03.I03",
    "GET /api/samples/{id}": "M03.F03.I02",
    "PUT /api/samples/{id}": "M03.F03.I04",
    "DELETE /api/samples/{id}": "M03.F03.I05",
    "PUT /api/samples/{id}/ext": "M03.F01.I07",
    "GET /api/test-records": "M03.F03.I06",
    "POST /api/test-records": "M03.F03.I08",
    "GET /api/test-records/{id}": "M03.F03.I07",
    "PUT /api/test-records/{id}": "M03.F03.I09",
    "DELETE /api/test-records/{id}": "M03.F03.I10",
    "PATCH /api/test-records/{id}/verdict": "M03.F03.I11",
    # T7 参数界面域 8 op（CRUD 5 + link/unlink/list-links；unlink 锚 M06.F03.I07）
    "GET /api/param-interfaces": "M06.F08.I01",
    "POST /api/param-interfaces": "M06.F08.I03",
    "GET /api/param-interfaces/{code}": "M06.F08.I02",
    "PUT /api/param-interfaces/{code}": "M06.F08.I04",
    "DELETE /api/param-interfaces/{code}": "M06.F08.I05",
    "POST /api/param-interfaces/links": "M06.F08.I06",
    "DELETE /api/param-interfaces/links": "M06.F03.I07",
    # GET /api/param-interfaces/links 为契约豁免辅助端点（.tsp 注记 _exempt §2）不挂 ID
    # T4 基础数据码表域 16 op（4 实体同构 CRUD）
    "GET /api/catalog/brands": "M04.F09.I01",
    "POST /api/catalog/brands": "M04.F09.I02",
    "PUT /api/catalog/brands/{code}": "M04.F09.I03",
    "DELETE /api/catalog/brands/{code}": "M04.F09.I04",
    "GET /api/catalog/grades": "M04.F08.I01",
    "POST /api/catalog/grades": "M04.F08.I02",
    "PUT /api/catalog/grades/{code}": "M04.F08.I03",
    "DELETE /api/catalog/grades/{code}": "M04.F08.I04",
    "GET /api/catalog/models": "M04.F06.I01",
    "POST /api/catalog/models": "M04.F06.I02",
    "PUT /api/catalog/models/{code}": "M04.F06.I03",
    "DELETE /api/catalog/models/{code}": "M04.F06.I04",
    "GET /api/catalog/specs": "M04.F07.I01",
    "POST /api/catalog/specs": "M04.F07.I02",
    "PUT /api/catalog/specs/{code}": "M04.F07.I03",
    "DELETE /api/catalog/specs/{code}": "M04.F07.I04",
    # T3 检测字典域 28 op（shared function-tree 现行锚，lab-go REQ-2026-004 同款）
    "GET /api/inspection/specialties": "M06.F01.I01",
    "POST /api/inspection/specialties": "M06.F01.I02",
    "PUT /api/inspection/specialties/{code}": "M06.F01.I03",
    "DELETE /api/inspection/specialties/{code}": "M06.F01.I04",
    "GET /api/inspection/objects": "M06.F02.I01",
    "POST /api/inspection/objects": "M06.F02.I02",
    "PUT /api/inspection/objects/{code}": "M06.F02.I03",
    "DELETE /api/inspection/objects/{code}": "M06.F02.I04",
    "GET /api/inspection/parameters": "M06.F03.I01",
    "POST /api/inspection/parameters": "M06.F03.I02",
    "PUT /api/inspection/parameters/{code}": "M06.F03.I03",
    "DELETE /api/inspection/parameters/{code}": "M06.F03.I04",
    "GET /api/inspection/standards": "M06.F04.I01",
    "POST /api/inspection/standards": "M06.F04.I02",
    "PUT /api/inspection/standards/{code}": "M06.F04.I03",
    "DELETE /api/inspection/standards/{code}": "M06.F04.I04",
    "POST /api/inspection/links/specialty-object": "M06.F02.I05",
    "DELETE /api/inspection/links/specialty-object": "M06.F02.I06",
    "GET /api/inspection/links/specialty-object": "M06.F02.I09",
    "POST /api/inspection/links/object-parameter": "M06.F02.I07",
    "DELETE /api/inspection/links/object-parameter": "M06.F02.I08",
    "GET /api/inspection/links/object-parameter": "M06.F02.I10",
    "POST /api/inspection/links/object-standard": "M06.F01.I05",
    "DELETE /api/inspection/links/object-standard": "M06.F01.I06",
    "GET /api/inspection/links/object-standard": "M06.F01.I07",
    "POST /api/inspection/links/standard-parameter": "M06.F03.I05",
    "DELETE /api/inspection/links/standard-parameter": "M06.F03.I06",
    "GET /api/inspection/links/standard-parameter": "M06.F03.I08",
}


def _walk(patterns: list, prefix: str = ""):
    for p in patterns:
        if isinstance(p, URLPattern):
            yield prefix + str(p.pattern)
        elif isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))


def _normalize(route: str) -> str:
    return (
        ("/" + route)
        .replace("<str:contract_id>", "{id}")
        .replace("<str:receipt_id>", "{id}")
        .replace("<str:sample_id>", "{id}")
        .replace("<str:record_id>", "{id}")
        .replace("<str:code>", "{code}")
        .rstrip("/")
    )


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
