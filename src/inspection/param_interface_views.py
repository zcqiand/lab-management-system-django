"""M06.F08 参数界面域 views + service —— rails ParamInterfaceService /
ParamInterfaceJunctions 镜像（平台级字典，无 tenant_id；junction 复用 T3 helpers）。

- list：keyword lower contains code/name；order (sort_order, code)；回显信封
  page??1、pageSize 缺省 = len(items)（rails 分叉，勿套 receipts 的 20）
- create：code + componentPath 必填 400；sortOrder 默认 0
- update：nil-skip PATCH；updated_at 恒刷；delete miss→404
- DTO：config 非 dict 回退 {}（响应恒对象）；NON_NULL 剔 None
- links：POST=upsert（PK=parameter+interface）恒 204；DELETE=幂等 no-op 204
  （rails `&.destroy!` 镜像）；GET=短信封 page=1/pageSize=len + 双 query 过滤
"""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError, NotFoundError
from entities.models import InspectionParamInterfaceLinks, InspectionParamInterfaces
from inspection.helpers import (
    now_iso,
    require_login_claims,
    require_non_blank,
    unlink_junction,
    upsert_junction,
)
from receipts.service import clean_dto

FIELDS = ("name", "componentPath", "description", "isOfficial", "sortOrder", "config")


def _camel_to_attr(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _body(request: Request) -> dict[str, Any]:
    data = getattr(request, "data", None)
    return data if isinstance(data, dict) else {}


def _query(request: Request, name: str) -> str | None:
    value = request.GET.get(name)
    return value if value else None


def _int_param(request: Request, name: str, default: int) -> int:
    raw = request.GET.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise BadRequestError("invalid integer value") from None


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------


def _found(code: str) -> InspectionParamInterfaces:
    row = InspectionParamInterfaces.objects.filter(code=code).first()
    if row is None:
        raise NotFoundError(f"ParamInterface not found: {code}")
    return row


def _dto(row: InspectionParamInterfaces) -> dict[str, Any]:
    result = clean_dto(
        {
            "code": row.code,
            "name": row.name,
            "componentPath": row.component_path,
            "description": row.description,
            "isOfficial": row.is_official,
            "sortOrder": row.sort_order,
            "config": row.config if isinstance(row.config, dict) else {},
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }
    )
    assert isinstance(result, dict)
    return result


def list_items(keyword: str | None) -> list[dict[str, Any]]:
    rows = list(InspectionParamInterfaces.objects.all().order_by("sort_order", "code"))
    if keyword:
        needle = keyword.lower()
        rows = [
            r for r in rows if needle in (r.code or "").lower() or needle in (r.name or "").lower()
        ]
    return [_dto(r) for r in rows]


def create(body: dict[str, Any]) -> dict[str, Any]:
    require_non_blank(**{"code": body.get("code"), "componentPath": body.get("componentPath")})
    if body.get("code") is None or body.get("componentPath") is None:
        raise BadRequestError("code and componentPath are required")
    now = now_iso()
    row = InspectionParamInterfaces.objects.create(
        code=body["code"],
        name=body.get("name"),
        component_path=body["componentPath"],
        description=body.get("description"),
        is_official=body.get("isOfficial"),
        sort_order=body.get("sortOrder") or 0,
        config=body.get("config"),
        created_at=now,
        updated_at=now,
    )
    return _dto(row)


def update(code: str, body: dict[str, Any]) -> dict[str, Any]:
    row = _found(code)
    for field in FIELDS:
        value = body.get(field)
        if value is not None:
            setattr(row, _camel_to_attr(field), value)
    row.updated_at = now_iso()
    row.save()
    return _dto(row)


def delete(code: str) -> None:
    _found(code).delete()


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def param_interfaces(request: Request) -> Response:
    require_login_claims(request)
    if request.method == "POST":
        return Response(create(_body(request)), status=200)
    items = list_items(_query(request, "keyword"))
    return Response(
        {
            "items": items,
            "page": _int_param(request, "page", 1),
            "pageSize": _int_param(request, "pageSize", len(items)),
            "total": len(items),
        }
    )


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([AllowAny])
def param_interface_detail(request: Request, code: str) -> Response:
    require_login_claims(request)
    if request.method == "GET":
        return Response(_dto(_found(code)))
    if request.method == "PUT":
        return Response(update(code, _body(request)))
    delete(code)
    return Response(status=204)


@api_view(["POST", "DELETE", "GET"])
@permission_classes([AllowAny])
def param_interface_links(request: Request) -> Response:
    require_login_claims(request)
    if request.method == "POST":
        body = _body(request)
        require_non_blank(
            **{
                "inspectionParameterCode": body.get("inspectionParameterCode"),
                "paramInterfaceCode": body.get("paramInterfaceCode"),
            }
        )
        if body.get("inspectionParameterCode") is None or body.get("paramInterfaceCode") is None:
            raise BadRequestError("junction link fields must be non-blank")
        upsert_junction(
            InspectionParamInterfaceLinks,
            key_values={
                "inspection_parameter_code": body["inspectionParameterCode"],
                "param_interface_code": body["paramInterfaceCode"],
            },
            payload_values={
                "report_name_code": body.get("reportNameCode"),
                "config": body.get("config"),
            },
        )
        return Response(status=204)
    if request.method == "DELETE":
        body = _body(request)
        unlink_junction(
            InspectionParamInterfaceLinks,
            key_values={
                "inspection_parameter_code": body.get("inspectionParameterCode"),
                "param_interface_code": body.get("paramInterfaceCode"),
            },
        )
        return Response(status=204)
    rows = list(InspectionParamInterfaceLinks.objects.all().order_by("updated_at"))
    p_code = _query(request, "inspectionParameterCode")
    i_code = _query(request, "paramInterfaceCode")
    if p_code:
        rows = [r for r in rows if r.inspection_parameter_code == p_code]
    if i_code:
        rows = [r for r in rows if r.param_interface_code == i_code]
    items = [
        clean_dto(
            {
                "inspectionParameterCode": r.inspection_parameter_code,
                "paramInterfaceCode": r.param_interface_code,
                "reportNameCode": r.report_name_code,
                "config": r.config,
            }
        )
        for r in rows
    ]
    return Response({"items": items, "page": 1, "pageSize": len(items), "total": len(items)})
