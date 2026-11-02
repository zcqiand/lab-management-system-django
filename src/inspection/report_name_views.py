"""M06.F07 报告名称域 views + service —— rails InspectionReportNameService /
ReportNameJunctions 逐条镜像（平台级字典无 tenant_id；junction 复用 T3 helpers）。

- list：keyword lower contains code/name；order (sort_order, code)；字典信封
  page??1、pageSize 缺省 = len(items)
- create：code/name 必填 400；**create=JPA merge**（同 code 覆盖整行含
  createdAt——rails 2026-09-29 live 共库对拍实锤，码表 overwrite 裁定同族）
- update：truthy 族跳 None；updated_at 恒刷；delete miss→404
- DTO：extFields 非 list 回退 []（响应恒数组）；NON_NULL 剔 None
- junction ×3：POST=upsert 恒 204（standard junction role 入 PK）；DELETE=幂等
  no-op 204；GET=短信封 page=1/pageSize=len（三组 GET 均契约豁免辅助端点）
"""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError, NotFoundError
from entities.models import (
    InspectionObjectReportNames,
    InspectionReportNameParameters,
    InspectionReportNames,
    InspectionReportNameStandards,
)
from inspection.helpers import (
    now_iso,
    require_login_claims,
    unlink_junction,
    upsert_junction,
)
from receipts.service import clean_dto

FIELDS = (
    "name",
    "fullName",
    "templatePath",
    "summaryName",
    "extFields",
    "description",
    "sortOrder",
)


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


def _dto(row: InspectionReportNames) -> dict[str, Any]:
    result = clean_dto(
        {
            "code": row.code,
            "name": row.name,
            "fullName": row.full_name,
            "templatePath": row.template_path,
            "summaryName": row.summary_name,
            "extFields": row.ext_fields if isinstance(row.ext_fields, list) else [],
            "description": row.description,
            "sortOrder": row.sort_order,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }
    )
    assert isinstance(result, dict)
    return result


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------


def _found(code: str) -> InspectionReportNames:
    try:
        return InspectionReportNames.objects.get(code=code)
    except InspectionReportNames.DoesNotExist:
        raise NotFoundError(f"ReportName not found: {code}") from None


def list_items(keyword: str | None) -> list[dict[str, Any]]:
    rows = list(InspectionReportNames.objects.all().order_by("sort_order", "code"))
    if keyword:
        needle = keyword.lower()
        rows = [
            r for r in rows if needle in (r.code or "").lower() or needle in (r.name or "").lower()
        ]
    return [_dto(r) for r in rows]


def create(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("code") is None or body.get("name") is None:
        raise BadRequestError("code and name are required")
    now = now_iso()
    values = {
        "name": body["name"],
        "full_name": body.get("fullName"),
        "template_path": body.get("templatePath"),
        "summary_name": body.get("summaryName"),
        "ext_fields": body.get("extFields"),
        "description": body.get("description"),
        "sort_order": body.get("sortOrder") or 0,
        "created_at": now,
        "updated_at": now,
    }
    # springboot repo.save = JPA merge 镜像：同 code 覆盖整行（含 createdAt）；
    # 共库四方对拍下先建方已占 code，裸 insert 会 UniqueViolation 500
    row = InspectionReportNames.objects.filter(code=body["code"]).first()
    if row is None:
        row = InspectionReportNames(code=body["code"], **values)
    else:
        for k, v in values.items():
            setattr(row, k, v)
    row.save()
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
def report_names(request: Request) -> Response:
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
def report_name_detail(request: Request, code: str) -> Response:
    require_login_claims(request)
    if request.method == "GET":
        return Response(_dto(_found(code)))
    if request.method == "PUT":
        return Response(update(code, _body(request)))
    delete(code)
    return Response(status=204)


def _junction_envelope(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items, "page": 1, "pageSize": len(items), "total": len(items)}


@api_view(["POST", "DELETE", "GET"])
@permission_classes([AllowAny])
def object_links(request: Request) -> Response:
    require_login_claims(request)
    body = _body(request)
    if request.method == "POST":
        if body.get("inspectionObjectCode") is None or body.get("reportNameCode") is None:
            raise BadRequestError("junction link fields must be non-blank")
        upsert_junction(
            InspectionObjectReportNames,
            key_values={
                "inspection_object_code": body["inspectionObjectCode"],
                "report_name_code": body["reportNameCode"],
            },
            payload_values={"remark": body.get("remark")},
        )
        return Response(status=204)
    if request.method == "DELETE":
        unlink_junction(
            InspectionObjectReportNames,
            key_values={
                "inspection_object_code": body.get("inspectionObjectCode"),
                "report_name_code": body.get("reportNameCode"),
            },
        )
        return Response(status=204)
    rows = list(InspectionObjectReportNames.objects.all().order_by("report_name_code"))
    o = _query(request, "inspectionObjectCode")
    r = _query(request, "reportNameCode")
    if o:
        rows = [x for x in rows if x.inspection_object_code == o]
    if r:
        rows = [x for x in rows if x.report_name_code == r]
    items = [
        clean_dto(
            {
                "inspectionObjectCode": x.inspection_object_code,
                "reportNameCode": x.report_name_code,
                "remark": x.remark,
            }
        )
        for x in rows
    ]
    return Response(_junction_envelope(items))


@api_view(["POST", "DELETE", "GET"])
@permission_classes([AllowAny])
def standard_links(request: Request) -> Response:
    require_login_claims(request)
    body = _body(request)
    if request.method == "POST":
        if (
            body.get("reportNameCode") is None
            or body.get("inspectionStandardCode") is None
            or body.get("role") is None
        ):
            raise BadRequestError("junction link fields must be non-blank")
        upsert_junction(
            InspectionReportNameStandards,
            key_values={
                "report_name_code": body["reportNameCode"],
                "inspection_standard_code": body["inspectionStandardCode"],
                "role": body["role"],
            },
            payload_values={"remark": body.get("remark")},
        )
        return Response(status=204)
    if request.method == "DELETE":
        unlink_junction(
            InspectionReportNameStandards,
            key_values={
                "report_name_code": body.get("reportNameCode"),
                "inspection_standard_code": body.get("inspectionStandardCode"),
                "role": body.get("role"),
            },
        )
        return Response(status=204)
    rows = list(InspectionReportNameStandards.objects.all().order_by("updated_at"))
    rn = _query(request, "reportNameCode")
    role = _query(request, "role")
    if rn:
        rows = [x for x in rows if x.report_name_code == rn]
    if role:
        rows = [x for x in rows if x.role == role]
    items = [
        clean_dto(
            {
                "reportNameCode": x.report_name_code,
                "inspectionStandardCode": x.inspection_standard_code,
                "role": x.role,
                "remark": x.remark,
            }
        )
        for x in rows
    ]
    return Response(_junction_envelope(items))


@api_view(["POST", "DELETE", "GET"])
@permission_classes([AllowAny])
def parameter_links(request: Request) -> Response:
    require_login_claims(request)
    body = _body(request)
    if request.method == "POST":
        if body.get("reportNameCode") is None or body.get("inspectionParameterCode") is None:
            raise BadRequestError("junction link fields must be non-blank")
        upsert_junction(
            InspectionReportNameParameters,
            key_values={
                "report_name_code": body["reportNameCode"],
                "inspection_parameter_code": body["inspectionParameterCode"],
            },
            payload_values={"remark": body.get("remark")},
        )
        return Response(status=204)
    if request.method == "DELETE":
        unlink_junction(
            InspectionReportNameParameters,
            key_values={
                "report_name_code": body.get("reportNameCode"),
                "inspection_parameter_code": body.get("inspectionParameterCode"),
            },
        )
        return Response(status=204)
    rows = list(InspectionReportNameParameters.objects.all().order_by("updated_at"))
    rn = _query(request, "reportNameCode")
    p = _query(request, "inspectionParameterCode")
    if rn:
        rows = [x for x in rows if x.report_name_code == rn]
    if p:
        rows = [x for x in rows if x.inspection_parameter_code == p]
    items = [
        clean_dto(
            {
                "reportNameCode": x.report_name_code,
                "inspectionParameterCode": x.inspection_parameter_code,
                "remark": x.remark,
            }
        )
        for x in rows
    ]
    return Response(_junction_envelope(items))
