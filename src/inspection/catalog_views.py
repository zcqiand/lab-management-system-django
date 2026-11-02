"""基础数据码表 16 端点 views —— rails app/services/catalog/catalog_service.rb 逐条
镜像（T4 初版镜像 fastapi impl/inspection_catalog_impl.py，Final review C-1 裁定
改随 rails/springboot 参照：撞全局 code PK 收敛 400，不 merge 不劫持租户）。

4 表（models=M04.F06 型号 / specs=F07 规格 / grades=F08 等级 / brands=F09 牌号）
同构，family 表驱动合并（fastapi _Family 同款）：

- tenant 收口：list 按 tenant 等值；update/delete 按 tenant+code 定位，他人租户行
  miss → 404（隔离）
- create = 裸 create（rails create! 同款）：撞全局 code 唯一约束 → IntegrityError
  → 全局 handler 400 "constraint violation"（sortOrder 默认 0）；返回 200。
  fastapi 的 merge+租户改写语义为家族在册分叉（跨租户撞码会劫持他人租户行）不随
- update = PATCH（None 跳过）+ updatedAt 刷新
- delete 命中 204 / miss 404
- list 回显域分页：items 全量、page??1、pageSize??len、total=len，ORDER BY
  sort_order,code；keyword lower contains code/name
- DTO 出口 NON_NULL：None 键缺席

鉴权：码表租户收口面——decode-only bearer + tenant_id claim 缺省 directory 默认租户
（fastapi current_tenant_or_default 镜像，helpers 同款）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError
from entities.models import InspectionBrands, InspectionGrades, InspectionModels, InspectionSpecs
from inspection.helpers import (
    current_tenant_or_default,
    keyword_hit,
    now_iso,
    require_login_claims,
    require_non_blank,
    scoped_row_or_404,
)


def _body(request: Request) -> dict[str, Any]:
    data = getattr(request, "data", None)
    return data if isinstance(data, dict) else {}


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """NON_NULL 出口镜像：None 键缺席（pydantic exclude_none 语义）。"""
    return {k: v for k, v in d.items() if v is not None}


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        raise BadRequestError("invalid integer value") from None


def _query_int(request: Request, name: str) -> int | None:
    raw = request.GET.get(name)
    return None if raw is None else _int(raw)


def _dto(row: Any) -> dict[str, Any]:
    return _clean(
        {
            "code": row.code,
            "tenantId": row.tenant_id,
            "inspectionObjectCode": row.inspection_object_code,
            "name": row.name,
            "remark": row.remark,
            "sortOrder": row.sort_order,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }
    )


@dataclass(frozen=True)
class _Family:
    """一个码表家族 = 实体 + 404 文案标签（springboot NSEE "Brand not found" 镜像）。"""

    entity: type[Any]
    label: str


_FAMILIES: dict[str, _Family] = {
    "brands": _Family(InspectionBrands, "Brand"),
    "grades": _Family(InspectionGrades, "Grade"),
    "models": _Family(InspectionModels, "Model"),
    "specs": _Family(InspectionSpecs, "Spec"),
}


def _list(fam: _Family, request: Request, claims: dict[str, Any]) -> Response:
    """Repository filter 镜像：tenant 等值 + objectCode/keyword 非空才过滤，
    ORDER BY sort_order,code；Page 包裹 page??1 / pageSize??len / total=len，
    items 恒全量（回显域，5.127③ 定稿表）。"""
    tenant = current_tenant_or_default(claims)
    rows = sorted(
        fam.entity.objects.filter(tenant_id=tenant),
        key=lambda r: (r.sort_order, r.code),
    )
    object_code = request.GET.get("inspectionObjectCode")
    if object_code:
        rows = [r for r in rows if r.inspection_object_code == object_code]
    keyword = request.GET.get("keyword")
    if keyword:
        rows = [r for r in rows if keyword_hit(keyword, r.code, r.name)]
    page = _query_int(request, "page")
    page_size = _query_int(request, "pageSize")
    items = [_dto(r) for r in rows]
    return Response(
        {
            "items": items,
            "page": page if page is not None else 1,
            "pageSize": page_size if page_size is not None else len(items),
            "total": len(items),
        }
    )


def _create(fam: _Family, request: Request, claims: dict[str, Any]) -> Response:
    """裸 create（rails create! 镜像）：撞全局 code 唯一约束 IntegrityError →
    全局 handler 400 "constraint violation"（Final review C-1：不 merge——原
    filter(code) 探测会跨租户劫持他人租户行；fastapi merge 分叉不随）。"""
    body = _body(request)
    require_non_blank(code=body.get("code"), name=body.get("name"))
    tenant = current_tenant_or_default(claims)
    now = now_iso()
    sort_order = _int(body.get("sortOrder"))
    row = fam.entity.objects.create(
        code=body["code"],
        tenant_id=tenant,
        inspection_object_code=body.get("inspectionObjectCode"),
        name=body["name"],
        remark=body.get("remark"),
        sort_order=sort_order if sort_order is not None else 0,
        created_at=now,
        updated_at=now,
    )
    return Response(_dto(row), status=200)


def _update(fam: _Family, request: Request, code: str, claims: dict[str, Any]) -> Response:
    """applyUpdate 镜像：PATCH（None 跳过）+ updatedAt=now。"""
    tenant = current_tenant_or_default(claims)
    row = scoped_row_or_404(fam.entity, code, tenant, fam.label)
    body = _body(request)
    if "inspectionObjectCode" in body and body["inspectionObjectCode"] is not None:
        row.inspection_object_code = body["inspectionObjectCode"]
    if body.get("name") is not None:
        row.name = body["name"]
    if "remark" in body and body["remark"] is not None:
        row.remark = body["remark"]
    sort_order = _int(body.get("sortOrder"))
    if sort_order is not None:
        row.sort_order = sort_order
    row.updated_at = now_iso()
    row.save()
    return Response(_dto(row), status=200)


def _delete(fam: _Family, code: str, claims: dict[str, Any]) -> Response:
    """Service delete 镜像：miss → 404；命中删除（204 由 view 收口）。"""
    tenant = current_tenant_or_default(claims)
    row = scoped_row_or_404(fam.entity, code, tenant, fam.label)
    row.delete()
    return Response(status=204)


def _make_dispatchers(name: str, fam: _Family) -> tuple[Callable[..., Any], Callable[..., Any]]:
    """一对 path 级 dispatcher（collection GET/POST + detail PUT/DELETE），
    DRF @api_view 405 语义保留：声明外方法仍 405。
    __name__ 先赋再装饰（django-stubs 把 @api_view 视作 AsView，装饰后无 __name__）。"""

    def collection(request: Request) -> Response:
        claims = require_login_claims(request)
        if request.method == "POST":
            return _create(fam, request, claims)
        return _list(fam, request, claims)

    def detail(request: Request, code: str) -> Response:
        claims = require_login_claims(request)
        if request.method == "DELETE":
            return _delete(fam, code, claims)
        return _update(fam, request, code, claims)

    collection.__name__ = f"catalog_{name}"
    detail.__name__ = f"catalog_{name}_detail"

    return (
        api_view(["GET", "POST"])(permission_classes([AllowAny])(collection)),
        api_view(["PUT", "DELETE"])(permission_classes([AllowAny])(detail)),
    )


catalog_brands, catalog_brand_detail = _make_dispatchers("brands", _FAMILIES["brands"])
catalog_grades, catalog_grade_detail = _make_dispatchers("grades", _FAMILIES["grades"])
catalog_models, catalog_model_detail = _make_dispatchers("models", _FAMILIES["models"])
catalog_specs, catalog_spec_detail = _make_dispatchers("specs", _FAMILIES["specs"])
