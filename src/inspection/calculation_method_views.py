"""M06.F05 计算方法域 views + service —— rails CalculationMethodService 逐条
镜像（平台级字典无 tenant_id，复合主键 object × parameter）。

- list：双过滤（inspectionObjectCode/inspectionParameterCode）+ order
  (sort_order, object, parameter)；裸数组（无分页信封，rails 分叉）
- create：双键任一缺失 400；**create=JPA merge**（同双键覆盖整行含
  createdAt）；缺省 algorithmType=manual / specimenCount=1 / sortOrder=0
- update：UPDATE_FIELDS truthy/strict 双判定（镜像 springboot mapper：
  truthy=值真值才写，strict=非 None 即写——specimenCount/sortOrder 可写 0）；
  updated_at 恒刷
- delete miss→404；DTO NON_NULL 递归剔 None（clean_dto）
"""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError, NotFoundError
from entities.models import InspectionCalculationMethods
from inspection.helpers import now_iso, require_login_claims
from receipts.service import clean_dto

# 镜像 CalculationMethodMapper.applyUpdate 的字段判定：
# truthy —— 值真值才写（字符串列）；strict —— 非 None 即写（数值列，可写 0）
UPDATE_FIELDS: dict[str, tuple[str, str]] = {
    "testingStandardCode": ("testing_standard_code", "truthy"),
    "reportNameCode": ("report_name_code", "truthy"),
    "algorithmType": ("algorithm_type", "truthy"),
    "specimenCount": ("specimen_count", "strict"),
    "formula": ("formula", "truthy"),
    "conditions": ("conditions", "truthy"),
    "roundingRule": ("rounding_rule", "truthy"),
    "remark": ("remark", "truthy"),
    "sortOrder": ("sort_order", "strict"),
}


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


def _dto(row: InspectionCalculationMethods) -> dict[str, Any]:
    result = clean_dto(
        {
            "inspectionObjectCode": row.inspection_object_code,
            "inspectionParameterCode": row.inspection_parameter_code,
            "testingStandardCode": row.testing_standard_code,
            "reportNameCode": row.report_name_code,
            "algorithmType": row.algorithm_type,
            "specimenCount": row.specimen_count,
            "formula": row.formula,
            "conditions": row.conditions,
            "roundingRule": row.rounding_rule,
            "remark": row.remark,
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


def _found(object_code: str, parameter_code: str) -> InspectionCalculationMethods:
    row = InspectionCalculationMethods.objects.filter(
        inspection_object_code=object_code, inspection_parameter_code=parameter_code
    ).first()
    if row is None:
        raise NotFoundError(f"CalculationMethod not found: {object_code}/{parameter_code}")
    return row


def list_items(object_code: str | None, parameter_code: str | None) -> list[dict[str, Any]]:
    rows = list(
        InspectionCalculationMethods.objects.all().order_by(
            "sort_order", "inspection_object_code", "inspection_parameter_code"
        )
    )
    if object_code:
        rows = [r for r in rows if r.inspection_object_code == object_code]
    if parameter_code:
        rows = [r for r in rows if r.inspection_parameter_code == parameter_code]
    return [_dto(r) for r in rows]


def create(body: dict[str, Any]) -> dict[str, Any]:
    object_code = body.get("inspectionObjectCode")
    parameter_code = body.get("inspectionParameterCode")
    if object_code is None or parameter_code is None:
        raise BadRequestError("inspectionObjectCode and inspectionParameterCode are required")
    now = now_iso()
    values = {
        "testing_standard_code": body.get("testingStandardCode"),
        "report_name_code": body.get("reportNameCode"),
        "algorithm_type": body.get("algorithmType") or "manual",
        "specimen_count": body.get("specimenCount") or 1,
        "formula": body.get("formula"),
        "conditions": body.get("conditions"),
        "rounding_rule": body.get("roundingRule"),
        "remark": body.get("remark"),
        "sort_order": body.get("sortOrder") or 0,
        "created_at": now,
        "updated_at": now,
    }
    # JPA merge 镜像：同双键覆盖整行（含 createdAt）。复合 PK 表禁 row.save()
    # （Django legacy 多 primary_key=True 只认首列作 Meta.pk，UPDATE WHERE 只按
    # 首列误伤兄弟行——T9 实锤），改走 queryset.update（WHERE 全键）
    key = {"inspection_object_code": object_code, "inspection_parameter_code": parameter_code}
    if not InspectionCalculationMethods.objects.filter(**key).update(**values):
        InspectionCalculationMethods.objects.create(**key, **values)
    return _dto(InspectionCalculationMethods.objects.get(**key))


def update(object_code: str, parameter_code: str, body: dict[str, Any]) -> dict[str, Any]:
    key = {"inspection_object_code": object_code, "inspection_parameter_code": parameter_code}
    values: dict[str, Any] = {}
    for json_key, (column, mode) in UPDATE_FIELDS.items():
        value = body.get(json_key)
        # truthy——值真值才写（字符串列）；strict——非 None 即写（数值列可写 0）
        if (mode == "truthy" and value) or (mode == "strict" and value is not None):
            values[column] = value
    values["updated_at"] = now_iso()
    if not InspectionCalculationMethods.objects.filter(**key).update(**values):
        raise NotFoundError(f"CalculationMethod not found: {object_code}/{parameter_code}")
    return _dto(InspectionCalculationMethods.objects.get(**key))


def delete(object_code: str, parameter_code: str) -> None:
    key = {"inspection_object_code": object_code, "inspection_parameter_code": parameter_code}
    if not InspectionCalculationMethods.objects.filter(**key).delete()[0]:
        raise NotFoundError(f"CalculationMethod not found: {object_code}/{parameter_code}")


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def calculation_methods(request: Request) -> Response:
    require_login_claims(request)
    if request.method == "POST":
        return Response(create(_body(request)), status=200)
    items = list_items(
        _query(request, "inspectionObjectCode"), _query(request, "inspectionParameterCode")
    )
    return Response(items)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([AllowAny])
def calculation_method_detail(
    request: Request, inspection_object_code: str, inspection_parameter_code: str
) -> Response:
    require_login_claims(request)
    if request.method == "GET":
        return Response(_dto(_found(inspection_object_code, inspection_parameter_code)))
    if request.method == "PUT":
        return Response(update(inspection_object_code, inspection_parameter_code, _body(request)))
    delete(inspection_object_code, inspection_parameter_code)
    return Response(status=204)
