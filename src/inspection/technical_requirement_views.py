"""M06.F06 技术要求域 views + service —— rails TechnicalRequirementService /
TechnicalRequirementFields 逐条镜像（tenant-scoped，复合主键
object × parameter × standard）。

- list：4 过滤（object/parameter/standard/verificationStatus）+ tenant 收口
  （claim 优先缺省 directory 默认租户）；order (sort_order, object, parameter,
  standard)；裸数组（无分页信封）
- create：三键任一缺失 400；**create=JPA merge**（同三键+同租户覆盖整行含
  createdAt——springboot repo.save 镜像，T4 码表 overwrite 裁定同族）；
  枚举缺省 valueType=numeric / comparison=≥ / judgmentMode=manual /
  verificationStatus=draft（`body[k] || default`）；NULLABLE 15 键直透；
  sortOrder 默认 0
- update：全字段跳 None（mapper `!= null` 镜像）；updated_at 恒刷
- delete miss→404；隔离：他人租户行 miss → 404 境外不可见
- DTO：NON_NULL 递归剔 None（clean_dto）
"""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError, NotFoundError
from entities.models import InspectionTechnicalRequirements
from inspection.helpers import (
    current_tenant_or_default,
    now_iso,
    require_login_claims,
)
from receipts.service import clean_dto

ENUM_DEFAULTS = {
    "valueType": "numeric",
    "comparison": "≥",
    "judgmentMode": "manual",
    "verificationStatus": "draft",
}

# 无缺省、直透 body 的可空列（rails NULLABLE 15 键）
NULLABLE = (
    "conditions",
    "minValue",
    "maxValue",
    "targetValue",
    "expression",
    "unit",
    "clause",
    "sourcePage",
    "sourceHash",
    "brand",
    "model",
    "grade",
    "spec",
    "sieve",
    "remark",
)

# mapper applyUpdate 全字段跳 None（含三键外的全部可变列）
UPDATE_FIELDS = ENUM_DEFAULTS.keys() | NULLABLE | {"sortOrder"}


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


def _dto(row: InspectionTechnicalRequirements) -> dict[str, Any]:
    result = clean_dto(
        {
            "tenantId": row.tenant_id,
            "inspectionObjectCode": row.inspection_object_code,
            "inspectionParameterCode": row.inspection_parameter_code,
            "judgmentStandardCode": row.judgment_standard_code,
            "conditions": row.conditions,
            "valueType": row.value_type,
            "minValue": row.min_value,
            "maxValue": row.max_value,
            "targetValue": row.target_value,
            "expression": row.expression,
            "unit": row.unit,
            "comparison": row.comparison,
            "judgmentMode": row.judgment_mode,
            "verificationStatus": row.verification_status,
            "clause": row.clause,
            "sourcePage": row.source_page,
            "sourceHash": row.source_hash,
            "brand": row.brand,
            "model": row.model,
            "grade": row.grade,
            "spec": row.spec,
            "sieve": row.sieve,
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


def _found(
    tenant: str, object_code: str, parameter_code: str, standard_code: str
) -> InspectionTechnicalRequirements:
    row = InspectionTechnicalRequirements.objects.filter(
        tenant_id=tenant,
        inspection_object_code=object_code,
        inspection_parameter_code=parameter_code,
        judgment_standard_code=standard_code,
    ).first()
    if row is None:
        raise NotFoundError(
            f"TechnicalRequirement not found: {object_code}/{parameter_code}/{standard_code}"
        )
    return row


def list_items(
    tenant: str,
    object_code: str | None,
    parameter_code: str | None,
    standard_code: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    rows = list(
        InspectionTechnicalRequirements.objects.filter(tenant_id=tenant).order_by(
            "sort_order",
            "inspection_object_code",
            "inspection_parameter_code",
            "judgment_standard_code",
        )
    )
    if object_code:
        rows = [r for r in rows if r.inspection_object_code == object_code]
    if parameter_code:
        rows = [r for r in rows if r.inspection_parameter_code == parameter_code]
    if standard_code:
        rows = [r for r in rows if r.judgment_standard_code == standard_code]
    if status:
        rows = [r for r in rows if r.verification_status == status]
    return [_dto(r) for r in rows]


def create(tenant: str, body: dict[str, Any]) -> dict[str, Any]:
    object_code = body.get("inspectionObjectCode")
    parameter_code = body.get("inspectionParameterCode")
    standard_code = body.get("judgmentStandardCode")
    if object_code is None or parameter_code is None or standard_code is None:
        raise BadRequestError(
            "inspectionObjectCode/inspectionParameterCode/judgmentStandardCode are required"
        )
    now = now_iso()
    values: dict[str, Any] = {}
    for field, default in ENUM_DEFAULTS.items():
        values[_camel_to_attr(field)] = body.get(field) or default  # `body[k] || default` 镜像
    for field in NULLABLE:
        values[_camel_to_attr(field)] = body.get(field)
    values["sort_order"] = body.get("sortOrder") or 0
    values["created_at"] = now
    values["updated_at"] = now
    # JPA merge 镜像：同三键+同租户覆盖整行（含 createdAt）。复合 PK 表禁
    # row.save()（Django legacy 多 primary_key=True 只认首列作 Meta.pk，UPDATE
    # WHERE 只按首列误伤兄弟行——T9 实锤），改走 queryset.update（WHERE 全键）
    key = {
        "tenant_id": tenant,
        "inspection_object_code": object_code,
        "inspection_parameter_code": parameter_code,
        "judgment_standard_code": standard_code,
    }
    if not InspectionTechnicalRequirements.objects.filter(**key).update(**values):
        InspectionTechnicalRequirements.objects.create(**key, **values)
    return _dto(InspectionTechnicalRequirements.objects.get(**key))


def update(
    tenant: str, object_code: str, parameter_code: str, standard_code: str, body: dict[str, Any]
) -> dict[str, Any]:
    key = {
        "tenant_id": tenant,
        "inspection_object_code": object_code,
        "inspection_parameter_code": parameter_code,
        "judgment_standard_code": standard_code,
    }
    values = {
        _camel_to_attr(field): value
        for field in UPDATE_FIELDS
        if (value := body.get(field)) is not None
    }
    values["updated_at"] = now_iso()
    if not InspectionTechnicalRequirements.objects.filter(**key).update(**values):
        raise NotFoundError(
            f"TechnicalRequirement not found: {object_code}/{parameter_code}/{standard_code}"
        )
    return _dto(InspectionTechnicalRequirements.objects.get(**key))


def delete(tenant: str, object_code: str, parameter_code: str, standard_code: str) -> None:
    key = {
        "tenant_id": tenant,
        "inspection_object_code": object_code,
        "inspection_parameter_code": parameter_code,
        "judgment_standard_code": standard_code,
    }
    if not InspectionTechnicalRequirements.objects.filter(**key).delete()[0]:
        raise NotFoundError(
            f"TechnicalRequirement not found: {object_code}/{parameter_code}/{standard_code}"
        )


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def technical_requirements(request: Request) -> Response:
    tenant = current_tenant_or_default(require_login_claims(request))
    if request.method == "POST":
        return Response(create(tenant, _body(request)), status=200)
    items = list_items(
        tenant,
        _query(request, "inspectionObjectCode"),
        _query(request, "inspectionParameterCode"),
        _query(request, "judgmentStandardCode"),
        _query(request, "verificationStatus"),
    )
    return Response(items)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([AllowAny])
def technical_requirement_detail(
    request: Request,
    inspection_object_code: str,
    inspection_parameter_code: str,
    judgment_standard_code: str,
) -> Response:
    tenant = current_tenant_or_default(require_login_claims(request))
    if request.method == "GET":
        return Response(
            _dto(
                _found(
                    tenant,
                    inspection_object_code,
                    inspection_parameter_code,
                    judgment_standard_code,
                )
            )
        )
    if request.method == "PUT":
        return Response(
            update(
                tenant,
                inspection_object_code,
                inspection_parameter_code,
                judgment_standard_code,
                _body(request),
            )
        )
    delete(tenant, inspection_object_code, inspection_parameter_code, judgment_standard_code)
    return Response(status=204)
