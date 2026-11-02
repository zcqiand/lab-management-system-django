"""检测字典面 28 端点 views —— fastapi impl/inspection_dictionary_impl.py 逐条镜像
（其注释标注参照 lab-springboot InspectionDictionaryService / InspectionJunctionService /
InspectionDictionaryMapper）。

- 实体列表：全量过滤后 Page 包裹不过滤（items=全量、page??1、pageSize??len、
  total=len）；排序 sort_order,code；keyword lower(code/name) contains
- 实体 POST：required 缺一 400 BAD_REQUEST；同 code 再 POST = JPA merge 全量覆盖
  （含时间戳刷新）；返回 200（非 201）
- 实体 PUT：PATCH 语义（白名单内局部合并，未提及字段不动），updatedAt 刷新
- junction：save()=upsert 覆盖全部载荷（含 None）、unlink 幂等 204；list 固定
  page=1、pageSize=size
- DTO 出口 NON_NULL 镜像：None 键缺席（_clean）

鉴权同 authn 薄壳形：AllowAny 公开挂载，逐端点显式 require_login（decode-only）。
"""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError
from entities.models import (
    InspectionObjectParameters,
    InspectionObjects,
    InspectionObjectStandards,
    InspectionParameters,
    InspectionSpecialties,
    InspectionSpecialtyObjects,
    InspectionStandardParameters,
    InspectionStandards,
)
from inspection.helpers import (
    get_or_404,
    keyword_hit,
    now_iso,
    require_login,
    require_non_blank,
    unlink_junction,
    upsert_junction,
)


def _body(request: Request) -> dict[str, Any]:
    data = getattr(request, "data", None)
    return data if isinstance(data, dict) else {}


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """NON_NULL 出口镜像：None 键缺席（pydantic exclude_none 语义）。"""
    return {k: v for k, v in d.items() if v is not None}


def _bool(value: Any) -> bool | None:
    """pydantic bool 宽松 coercion 镜像（bool/“true”/“1”）；None 透传。"""
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1"):
        return True
    if text in ("false", "0"):
        return False
    raise BadRequestError("invalid boolean value")


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        raise BadRequestError("invalid integer value") from None


def _query_int(request: Request, name: str) -> int | None:
    raw = request.GET.get(name)
    if raw is None:
        return None
    return _int(raw)


def _page(items: list[dict[str, Any]], page: int | None, page_size: int | None) -> dict[str, Any]:
    """Page 包裹不过滤镜像：page??1、pageSize??len、total=len。"""
    return {
        "items": items,
        "page": page if page is not None else 1,
        "pageSize": page_size if page_size is not None else len(items),
        "total": len(items),
    }


def _require(body: dict[str, Any], required: tuple[str, ...]) -> None:
    """契约必填缺一 → 400（message 列全必填，contracts 域同形）。"""
    missing = [f for f in required if not str(body.get(f) or "").strip()]
    if missing:
        raise BadRequestError(" / ".join(required) + " are required")


# === DTO 映射（InspectionDictionaryMapper.toDto 镜像，camelCase 出口 + NON_NULL） ===


def _specialty_dto(r: Any) -> dict[str, Any]:
    return _clean(
        {
            "code": r.code,
            "officialNo": r.official_no,
            "name": r.name,
            "isOfficial": r.is_official,
            "enabled": r.enabled,
            "sortOrder": r.sort_order,
            "createdAt": r.created_at,
            "updatedAt": r.updated_at,
        }
    )


def _object_dto(r: Any) -> dict[str, Any]:
    return _clean(
        {
            "code": r.code,
            "inspectionSpecialtyCode": r.inspection_specialty_code,
            "sourceProjectNo": r.source_project_no,
            "sourceProjectName": r.source_project_name,
            "name": r.name,
            "isOptionalForQualification": r.is_optional_for_qualification,
            "isOfficial": r.is_official,
            "enabled": r.enabled,
            "sortOrder": r.sort_order,
            "createdAt": r.created_at,
            "updatedAt": r.updated_at,
        }
    )


def _parameter_dto(r: Any) -> dict[str, Any]:
    return _clean(
        {
            "code": r.code,
            "name": r.name,
            "rawName": r.raw_name,
            "canonicalName": r.canonical_name,
            "methodText": r.method_text,
            "aliases": list(r.aliases or []),
            "unit": r.unit,
            "sourceType": r.source_type,
            "sortOrder": r.sort_order,
            "createdAt": r.created_at,
            "updatedAt": r.updated_at,
        }
    )


def _standard_dto(r: Any) -> dict[str, Any]:
    return _clean(
        {
            "code": r.code,
            "name": r.name,
            "version": r.version,
            "status": r.status,
            "sourceDocumentId": r.source_document_id,
            "sourceHash": r.source_hash,
            "sortOrder": r.sort_order,
            "createdAt": r.created_at,
            "updatedAt": r.updated_at,
        }
    )


# === 实体 create/update 公共骨架（JPA merge 语义镜像） ===


def _entity_create(
    model: type[Any],
    body: dict[str, Any],
    required: tuple[str, ...],
    column_values: dict[str, Any],
) -> None:
    """同 code 再 POST = 全量覆盖（含时间戳刷新，载荷含 None 也覆盖——JPA merge）。"""
    _require(body, required)
    code = str(body["code"])
    now = now_iso()
    row = model.objects.filter(code=code).first()
    if row is None:
        model.objects.create(code=code, created_at=now, updated_at=now, **column_values)
        return
    for k, v in column_values.items():
        setattr(row, k, v)
    row.created_at = now
    row.updated_at = now
    row.save()


def _entity_update(
    row: Any, body: dict[str, Any], updatable: dict[str, str], coercers: dict[str, Any]
) -> None:
    """PATCH 语义：白名单内且 body 提及（非 None）才写；updatedAt 刷新。"""
    for camel, attr in updatable.items():
        if camel not in body or body[camel] is None:
            continue
        coerce = coercers.get(camel)
        setattr(row, attr, coerce(body[camel]) if coerce is not None else body[camel])
    row.updated_at = now_iso()
    row.save()


# === M06.F01.I01 检测专项 ===


def list_specialties(request: Request) -> Response:
    require_login(request)
    keyword = request.GET.get("keyword")
    rows = sorted(InspectionSpecialties.objects.all(), key=lambda r: (r.sort_order, r.code))
    return Response(
        _page(
            [_specialty_dto(r) for r in rows if keyword_hit(keyword, r.code, r.name)],
            _query_int(request, "page"),
            _query_int(request, "pageSize"),
        )
    )


def create_specialty(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    _entity_create(
        InspectionSpecialties,
        body,
        ("code", "officialNo", "name"),
        {
            "official_no": body.get("officialNo"),
            "name": body.get("name"),
            "is_official": _bool(body.get("isOfficial"))
            if body.get("isOfficial") is not None
            else True,
            "enabled": _bool(body.get("enabled")) if body.get("enabled") is not None else True,
            "sort_order": _int(body.get("sortOrder")) if body.get("sortOrder") is not None else 0,
        },
    )
    return Response(_specialty_dto(InspectionSpecialties.objects.get(code=body["code"])))


def update_specialty(request: Request, code: str) -> Response:
    require_login(request)
    row = get_or_404(InspectionSpecialties, code)
    _entity_update(
        row,
        _body(request),
        {
            "officialNo": "official_no",
            "name": "name",
            "isOfficial": "is_official",
            "enabled": "enabled",
            "sortOrder": "sort_order",
        },
        {"isOfficial": _bool, "enabled": _bool, "sortOrder": _int},
    )
    return Response(_specialty_dto(row))


def delete_specialty(_request: Request, code: str) -> Response:
    require_login(_request)
    get_or_404(InspectionSpecialties, code).delete()
    return Response(status=204)


# === M06.F02.I01 检测项目 ===


def list_objects(request: Request) -> Response:
    require_login(request)
    keyword = request.GET.get("keyword")
    specialty_code = request.GET.get("inspectionSpecialtyCode")
    rows = sorted(InspectionObjects.objects.all(), key=lambda r: (r.sort_order, r.code))
    return Response(
        _page(
            [
                _object_dto(r)
                for r in rows
                if (specialty_code is None or r.inspection_specialty_code == specialty_code)
                and keyword_hit(keyword, r.code, r.name)
            ],
            _query_int(request, "page"),
            _query_int(request, "pageSize"),
        )
    )


def create_object(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    _entity_create(
        InspectionObjects,
        body,
        ("code", "inspectionSpecialtyCode", "sourceProjectNo", "sourceProjectName", "name"),
        {
            "inspection_specialty_code": body.get("inspectionSpecialtyCode"),
            "source_project_no": body.get("sourceProjectNo"),
            "source_project_name": body.get("sourceProjectName"),
            "name": body.get("name"),
            "is_optional_for_qualification": (
                _bool(body.get("isOptionalForQualification"))
                if body.get("isOptionalForQualification") is not None
                else False
            ),
            "is_official": _bool(body.get("isOfficial"))
            if body.get("isOfficial") is not None
            else True,
            "enabled": _bool(body.get("enabled")) if body.get("enabled") is not None else True,
            "sort_order": _int(body.get("sortOrder")) if body.get("sortOrder") is not None else 0,
        },
    )
    return Response(_object_dto(InspectionObjects.objects.get(code=body["code"])))


def update_object(request: Request, code: str) -> Response:
    require_login(request)
    row = get_or_404(InspectionObjects, code)
    _entity_update(
        row,
        _body(request),
        {
            "inspectionSpecialtyCode": "inspection_specialty_code",
            "sourceProjectNo": "source_project_no",
            "sourceProjectName": "source_project_name",
            "name": "name",
            "isOptionalForQualification": "is_optional_for_qualification",
            "isOfficial": "is_official",
            "enabled": "enabled",
            "sortOrder": "sort_order",
        },
        {
            "isOptionalForQualification": _bool,
            "isOfficial": _bool,
            "enabled": _bool,
            "sortOrder": _int,
        },
    )
    return Response(_object_dto(row))


def delete_object(_request: Request, code: str) -> Response:
    require_login(_request)
    get_or_404(InspectionObjects, code).delete()
    return Response(status=204)


# === M06.F03.I01 检测参数 ===


def list_parameters(request: Request) -> Response:
    require_login(request)
    keyword = request.GET.get("keyword")
    source_type = request.GET.get("sourceType")
    rows = sorted(InspectionParameters.objects.all(), key=lambda r: (r.sort_order, r.code))
    return Response(
        _page(
            [
                _parameter_dto(r)
                for r in rows
                if (source_type is None or r.source_type == source_type)
                and keyword_hit(keyword, r.code, r.name)
            ],
            _query_int(request, "page"),
            _query_int(request, "pageSize"),
        )
    )


def create_parameter(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    _entity_create(
        InspectionParameters,
        body,
        ("code", "name", "rawName", "canonicalName"),
        {
            "name": body.get("name"),
            "raw_name": body.get("rawName"),
            "canonical_name": body.get("canonicalName"),
            "method_text": body.get("methodText"),
            "aliases": [] if body.get("aliases") is None else body["aliases"],
            "unit": body.get("unit"),
            "source_type": (
                "official" if body.get("sourceType") is None else str(body["sourceType"])
            ),
            "sort_order": _int(body.get("sortOrder")) if body.get("sortOrder") is not None else 0,
        },
    )
    return Response(_parameter_dto(InspectionParameters.objects.get(code=body["code"])))


def update_parameter(request: Request, code: str) -> Response:
    require_login(request)
    row = get_or_404(InspectionParameters, code)
    _entity_update(
        row,
        _body(request),
        {
            "name": "name",
            "rawName": "raw_name",
            "canonicalName": "canonical_name",
            "methodText": "method_text",
            "aliases": "aliases",
            "unit": "unit",
            "sourceType": "source_type",
            "sortOrder": "sort_order",
        },
        {"sortOrder": _int},
    )
    return Response(_parameter_dto(row))


def delete_parameter(_request: Request, code: str) -> Response:
    require_login(_request)
    get_or_404(InspectionParameters, code).delete()
    return Response(status=204)


# === M06.F04.I01 检测标准 ===


def list_standards(request: Request) -> Response:
    require_login(request)
    keyword = request.GET.get("keyword")
    status = request.GET.get("status")
    rows = sorted(InspectionStandards.objects.all(), key=lambda r: (r.sort_order, r.code))
    return Response(
        _page(
            [
                _standard_dto(r)
                for r in rows
                if (status is None or r.status == status) and keyword_hit(keyword, r.code, r.name)
            ],
            _query_int(request, "page"),
            _query_int(request, "pageSize"),
        )
    )


def create_standard(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    _entity_create(
        InspectionStandards,
        body,
        ("code", "name"),
        {
            "name": body.get("name"),
            "version": body.get("version"),
            "status": "active" if body.get("status") is None else str(body["status"]),
            "source_document_id": body.get("sourceDocumentId"),
            "source_hash": body.get("sourceHash"),
            "sort_order": _int(body.get("sortOrder")) if body.get("sortOrder") is not None else 0,
        },
    )
    return Response(_standard_dto(InspectionStandards.objects.get(code=body["code"])))


def update_standard(request: Request, code: str) -> Response:
    require_login(request)
    row = get_or_404(InspectionStandards, code)
    _entity_update(
        row,
        _body(request),
        {
            "name": "name",
            "version": "version",
            "status": "status",
            "sourceDocumentId": "source_document_id",
            "sourceHash": "source_hash",
            "sortOrder": "sort_order",
        },
        {"sortOrder": _int},
    )
    return Response(_standard_dto(row))


def delete_standard(_request: Request, code: str) -> Response:
    require_login(_request)
    get_or_404(InspectionStandards, code).delete()
    return Response(status=204)


# === junction 家族：专项↔项目（M06.F02.I05） ===


def list_specialty_object_links(request: Request) -> Response:
    require_login(request)
    rows = list(InspectionSpecialtyObjects.objects.all())
    specialty_code = request.GET.get("inspectionSpecialtyCode")
    if specialty_code is not None:
        rows = [r for r in rows if r.inspection_specialty_code == specialty_code]
    items = [
        _clean(
            {
                "inspectionSpecialtyCode": r.inspection_specialty_code,
                "inspectionObjectCode": r.inspection_object_code,
                "remark": r.remark,
            }
        )
        for r in rows
    ]
    return Response({"items": items, "page": 1, "pageSize": len(items), "total": len(items)})


def link_specialty_object(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    require_non_blank(
        inspection_specialty_code=body.get("inspectionSpecialtyCode"),
        inspection_object_code=body.get("inspectionObjectCode"),
    )
    upsert_junction(
        InspectionSpecialtyObjects,
        key_values={
            "inspection_specialty_code": body["inspectionSpecialtyCode"],
            "inspection_object_code": body["inspectionObjectCode"],
        },
        payload_values={"remark": body.get("remark")},
    )
    return Response(status=204)


def unlink_specialty_object(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    unlink_junction(
        InspectionSpecialtyObjects,
        key_values={
            "inspection_specialty_code": body.get("inspectionSpecialtyCode"),
            "inspection_object_code": body.get("inspectionObjectCode"),
        },
    )
    return Response(status=204)


# === junction 家族：项目↔参数（M06.F02.I07，PK=(object, parameter)） ===


def list_object_parameter_links(request: Request) -> Response:
    require_login(request)
    rows = list(InspectionObjectParameters.objects.all())
    object_code = request.GET.get("inspectionObjectCode")
    parameter_code = request.GET.get("inspectionParameterCode")
    if object_code is not None:
        rows = [r for r in rows if r.inspection_object_code == object_code]
    if parameter_code is not None:
        rows = [r for r in rows if r.inspection_parameter_code == parameter_code]
    items = [
        _clean(
            {
                "inspectionObjectCode": r.inspection_object_code,
                "inspectionParameterCode": r.inspection_parameter_code,
                "qualificationLevel": r.qualification_level,
                "sourcePage": r.source_page,
                "remark": r.remark,
            }
        )
        for r in rows
    ]
    return Response({"items": items, "page": 1, "pageSize": len(items), "total": len(items)})


def link_object_parameter(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    require_non_blank(
        inspection_object_code=body.get("inspectionObjectCode"),
        inspection_parameter_code=body.get("inspectionParameterCode"),
    )
    # qualificationLevel 契约必填（缺省路径不可达，fastapi 澄清同款显式校验）
    require_non_blank(qualification_level=body.get("qualificationLevel"))
    upsert_junction(
        InspectionObjectParameters,
        key_values={
            "inspection_object_code": body["inspectionObjectCode"],
            "inspection_parameter_code": body["inspectionParameterCode"],
        },
        payload_values={
            "qualification_level": body["qualificationLevel"],
            "source_page": _int(body.get("sourcePage")),
            "remark": body.get("remark"),
        },
    )
    return Response(status=204)


def unlink_object_parameter(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    unlink_junction(
        InspectionObjectParameters,
        key_values={
            "inspection_object_code": body.get("inspectionObjectCode"),
            "inspection_parameter_code": body.get("inspectionParameterCode"),
        },
    )
    return Response(status=204)


# === junction 家族：项目↔标准（M06.F01.I05，role 是键部件） ===


def list_object_standard_links(request: Request) -> Response:
    require_login(request)
    rows = list(InspectionObjectStandards.objects.all())
    object_code = request.GET.get("inspectionObjectCode")
    role = request.GET.get("role")
    if object_code is not None:
        rows = [r for r in rows if r.inspection_object_code == object_code]
    if role is not None:
        rows = [r for r in rows if r.role == role]
    items = [
        _clean(
            {
                "inspectionObjectCode": r.inspection_object_code,
                "inspectionStandardCode": r.inspection_standard_code,
                "role": r.role,
                "remark": r.remark,
            }
        )
        for r in rows
    ]
    return Response({"items": items, "page": 1, "pageSize": len(items), "total": len(items)})


def link_object_standard(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    require_non_blank(
        inspection_object_code=body.get("inspectionObjectCode"),
        inspection_standard_code=body.get("inspectionStandardCode"),
        role=body.get("role"),
    )
    upsert_junction(
        InspectionObjectStandards,
        key_values={
            "inspection_object_code": body["inspectionObjectCode"],
            "inspection_standard_code": body["inspectionStandardCode"],
            "role": body["role"],
        },
        payload_values={"remark": body.get("remark")},
    )
    return Response(status=204)


def unlink_object_standard(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    unlink_junction(
        InspectionObjectStandards,
        key_values={
            "inspection_object_code": body.get("inspectionObjectCode"),
            "inspection_standard_code": body.get("inspectionStandardCode"),
            "role": body.get("role"),
        },
    )
    return Response(status=204)


# === junction 家族：标准↔参数（M06.F03.I05，纯键家族无载荷列） ===


def list_standard_parameter_links(request: Request) -> Response:
    require_login(request)
    rows = list(InspectionStandardParameters.objects.all())
    standard_code = request.GET.get("inspectionStandardCode")
    parameter_code = request.GET.get("inspectionParameterCode")
    if standard_code is not None:
        rows = [r for r in rows if r.inspection_standard_code == standard_code]
    if parameter_code is not None:
        rows = [r for r in rows if r.inspection_parameter_code == parameter_code]
    items = [
        {
            "inspectionStandardCode": r.inspection_standard_code,
            "inspectionParameterCode": r.inspection_parameter_code,
        }
        for r in rows
    ]
    return Response({"items": items, "page": 1, "pageSize": len(items), "total": len(items)})


def link_standard_parameter(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    require_non_blank(
        inspection_standard_code=body.get("inspectionStandardCode"),
        inspection_parameter_code=body.get("inspectionParameterCode"),
    )
    upsert_junction(
        InspectionStandardParameters,
        key_values={
            "inspection_standard_code": body["inspectionStandardCode"],
            "inspection_parameter_code": body["inspectionParameterCode"],
        },
        payload_values={},
    )
    return Response(status=204)


def unlink_standard_parameter(request: Request) -> Response:
    require_login(request)
    body = _body(request)
    unlink_junction(
        InspectionStandardParameters,
        key_values={
            "inspection_standard_code": body.get("inspectionStandardCode"),
            "inspection_parameter_code": body.get("inspectionParameterCode"),
        },
    )
    return Response(status=204)


# === 路径级分发（Django path 按 URL 路由不分方法——同路径多方法由本层收口，
# DRF @api_view 405 语义保留：声明外方法仍 405） ===


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def specialties(request: Request) -> Response:
    if request.method == "POST":
        return create_specialty(request)
    return list_specialties(request)


@api_view(["PUT", "DELETE"])
@permission_classes([AllowAny])
def specialty_detail(request: Request, code: str) -> Response:
    if request.method == "DELETE":
        return delete_specialty(request, code)
    return update_specialty(request, code)


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def objects(request: Request) -> Response:
    if request.method == "POST":
        return create_object(request)
    return list_objects(request)


@api_view(["PUT", "DELETE"])
@permission_classes([AllowAny])
def object_detail(request: Request, code: str) -> Response:
    if request.method == "DELETE":
        return delete_object(request, code)
    return update_object(request, code)


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def parameters(request: Request) -> Response:
    if request.method == "POST":
        return create_parameter(request)
    return list_parameters(request)


@api_view(["PUT", "DELETE"])
@permission_classes([AllowAny])
def parameter_detail(request: Request, code: str) -> Response:
    if request.method == "DELETE":
        return delete_parameter(request, code)
    return update_parameter(request, code)


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def standards(request: Request) -> Response:
    if request.method == "POST":
        return create_standard(request)
    return list_standards(request)


@api_view(["PUT", "DELETE"])
@permission_classes([AllowAny])
def standard_detail(request: Request, code: str) -> Response:
    if request.method == "DELETE":
        return delete_standard(request, code)
    return update_standard(request, code)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([AllowAny])
def specialty_object_links(request: Request) -> Response:
    if request.method == "POST":
        return link_specialty_object(request)
    if request.method == "DELETE":
        return unlink_specialty_object(request)
    return list_specialty_object_links(request)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([AllowAny])
def object_parameter_links(request: Request) -> Response:
    if request.method == "POST":
        return link_object_parameter(request)
    if request.method == "DELETE":
        return unlink_object_parameter(request)
    return list_object_parameter_links(request)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([AllowAny])
def object_standard_links(request: Request) -> Response:
    if request.method == "POST":
        return link_object_standard(request)
    if request.method == "DELETE":
        return unlink_object_standard(request)
    return list_object_standard_links(request)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([AllowAny])
def standard_parameter_links(request: Request) -> Response:
    if request.method == "POST":
        return link_standard_parameter(request)
    if request.method == "DELETE":
        return unlink_standard_parameter(request)
    return list_standard_parameter_links(request)
