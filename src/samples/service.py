"""样品 + 检测记录域 service —— rails Samples::SampleService /
TestRecords::TestRecordService 逐条镜像（其注释标注 lab-springboot 镜像）。

- samples：tenant-scoped + receipt FK 显式校验（miss→404 "Receipt not found"）；
  keyword lower contains sample_code/sample_name；order created_at DESC,
  sample_code ASC；create ext 默认 {}、id=「S-<uuid>」；update PATCH 跳 None
  （ext 非 None 才替换）；update_ext 整体替换且 ext 必填 400（5.89）
- test-records：create 四必填 400（rails 字面量）；sample/parameter/standard FK
  走 DB 约束（IntegrityError→400，rails InvalidForeignKey rescue 镜像）；order
  updated_at DESC, id ASC；update PATCH 跳 None；set_verdict 直写可置 null；
  id=「TR-<uuid>」
- DTO NON_NULL 递归（ext 例外：键恒在，空时 {}——rails dto `||{}` 镜像）
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import IntegrityError, transaction

from authn.errors import BadRequestError, NotFoundError
from entities.models import SampleReceipts, Samples, TestRecords
from receipts.service import clean_dto, now_iso

# camel 命名业务字段（rails UPDATE_FIELDS 镜像）：create/update 共用
SAMPLE_FIELDS = (
    "sampleName",
    "model",
    "specification",
    "grade",
    "brand",
    "manufacturer",
    "structuralPart",
    "representQuantity",
    "sampleQuantity",
    "batchNumber",
    "supplyUnit",
    "arrivalDate",
    "samplingDate",
    "curingCondition",
    "age",
    "remark",
)
RECORD_FIELDS = (
    "parameterCode",
    "standardCode",
    "requirementCode",
    "requirement",
    "result",
    "verdict",
)
RECORD_REQUIRED = ("sampleId", "parameterCode", "requirement", "result")


def _camel_to_attr(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


# ---------------------------------------------------------------------------
# samples（M03.F03.I01-I05 + M03.F01.I07 ext 补录）
# ---------------------------------------------------------------------------


def find_sample(tenant: str, sample_id: str) -> Samples:
    row = Samples.objects.filter(id=sample_id).first()
    if row is None or row.tenant_id != tenant:
        raise NotFoundError(f"Sample not found: {sample_id}")
    return row


def list_samples(tenant: str, receipt_id: str | None, keyword: str | None) -> list[dict[str, Any]]:
    rows = list(Samples.objects.filter(tenant_id=tenant).order_by("-created_at", "sample_code"))
    if receipt_id:
        rows = [r for r in rows if r.receipt_id == receipt_id]
    if keyword:
        needle = keyword.lower()
        rows = [
            r
            for r in rows
            if needle in (r.sample_code or "").lower() or needle in (r.sample_name or "").lower()
        ]
    return [sample_dto(r) for r in rows]


def create_sample(tenant: str, body: dict[str, Any]) -> dict[str, Any]:
    receipt_id = body.get("receiptId")
    if not SampleReceipts.objects.filter(id=receipt_id, tenant_id=tenant).exists():
        raise NotFoundError(f"Receipt not found: {receipt_id}")
    if not str(body.get("sampleCode") or "").strip():
        raise BadRequestError("sampleCode is required")
    now = now_iso()
    values: dict[str, Any] = {
        "id": f"S-{uuid.uuid4()}",
        "receipt_id": receipt_id,
        "tenant_id": tenant,
        "ext": body.get("ext") or {},
        "created_at": now,
        "updated_at": now,
    }
    for field in SAMPLE_FIELDS:
        values[_camel_to_attr(field)] = body.get(field)
    return sample_dto(Samples.objects.create(**values))


def update_sample(tenant: str, sample_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = find_sample(tenant, sample_id)
    for field in SAMPLE_FIELDS:
        value = body.get(field)
        if value is not None:
            setattr(row, _camel_to_attr(field), value)
    if body.get("ext") is not None:
        row.ext = body["ext"]
    row.updated_at = now_iso()
    row.save()
    return sample_dto(row)


def update_sample_ext(tenant: str, sample_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """M03.F01.I07 ext 补录：整体替换（合并是前端职责）；契约 ext 必填（5.89）。"""
    if body.get("ext") is None:
        raise BadRequestError("ext is required")
    row = find_sample(tenant, sample_id)
    row.ext = body["ext"]
    row.updated_at = now_iso()
    row.save()
    return sample_dto(row)


def delete_sample(tenant: str, sample_id: str) -> None:
    find_sample(tenant, sample_id).delete()


def get_sample(tenant: str, sample_id: str) -> dict[str, Any]:
    return sample_dto(find_sample(tenant, sample_id))


def sample_dto(row: Samples) -> dict[str, Any]:
    """rails dto 镜像（camelCase）；ext ||{} 恒在；NON_NULL 剔 None。"""
    payload: dict[str, Any] = {
        "id": row.id,
        "receiptId": row.receipt_id,
        "sampleCode": row.sample_code,
        "sampleName": row.sample_name,
        "model": row.model,
        "specification": row.specification,
        "grade": row.grade,
        "brand": row.brand,
        "manufacturer": row.manufacturer,
        "structuralPart": row.structural_part,
        "representQuantity": row.represent_quantity,
        "sampleQuantity": row.sample_quantity,
        "batchNumber": row.batch_number,
        "supplyUnit": row.supply_unit,
        "arrivalDate": row.arrival_date,
        "samplingDate": row.sampling_date,
        "curingCondition": row.curing_condition,
        "age": row.age,
        "ext": row.ext or {},
        "remark": row.remark,
        "tenantId": row.tenant_id,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }
    result = clean_dto(payload)
    assert isinstance(result, dict)
    return result


# ---------------------------------------------------------------------------
# test-records（M03.F03.I06-I11）
# ---------------------------------------------------------------------------


def find_record(tenant: str, record_id: str) -> TestRecords:
    row = TestRecords.objects.filter(id=record_id).first()
    if row is None or row.tenant_id != tenant:
        raise NotFoundError(f"TestRecord not found: {record_id}")
    return row


def list_records(tenant: str, sample_id: str | None) -> list[dict[str, Any]]:
    rows = list(TestRecords.objects.filter(tenant_id=tenant).order_by("-updated_at", "id"))
    if sample_id:
        rows = [r for r in rows if r.sample_id == sample_id]
    return [record_dto(r) for r in rows]


def create_record(tenant: str, body: dict[str, Any]) -> dict[str, Any]:
    missing = [f for f in RECORD_REQUIRED if body.get(f) is None]
    if missing:
        raise BadRequestError("sampleId, parameterCode, requirement and result are required")
    now = now_iso()
    values: dict[str, Any] = {
        "id": f"TR-{uuid.uuid4()}",
        "sample_id": body["sampleId"],
        "tenant_id": tenant,
        "created_at": now,
        "updated_at": now,
    }
    for field in RECORD_FIELDS:
        values[_camel_to_attr(field)] = body.get(field)
    try:
        with transaction.atomic():  # savepoint：IntegrityError 后外层事务仍可用
            row = TestRecords.objects.create(**values)
    except IntegrityError:
        # FK DB 约束镜像（rails InvalidForeignKey → 400）：sample/parameter/standard 引用不存在
        raise BadRequestError("sampleId, parameterCode or standardCode not found") from None
    return record_dto(row)


def update_record(tenant: str, record_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = find_record(tenant, record_id)
    for field in RECORD_FIELDS:
        value = body.get(field)
        if value is not None:
            setattr(row, _camel_to_attr(field), value)
    row.updated_at = now_iso()
    row.save()
    return record_dto(row)


def set_verdict(tenant: str, record_id: str, verdict: str | None) -> dict[str, Any]:
    """人工改判 verdict（M03.F05/F06 报告流程可触发）；直写（可置 null）。"""
    row = find_record(tenant, record_id)
    row.verdict = verdict
    row.updated_at = now_iso()
    row.save()
    return record_dto(row)


def delete_record(tenant: str, record_id: str) -> None:
    find_record(tenant, record_id).delete()


def get_record(tenant: str, record_id: str) -> dict[str, Any]:
    return record_dto(find_record(tenant, record_id))


def record_dto(row: TestRecords) -> dict[str, Any]:
    """rails dto 镜像（camelCase）；NON_NULL 剔 None（verdict null → 键不在）。"""
    payload: dict[str, Any] = {
        "id": row.id,
        "tenantId": row.tenant_id,
        "sampleId": row.sample_id,
        "parameterCode": row.parameter_code,
        "standardCode": row.standard_code,
        "requirementCode": row.requirement_code,
        "requirement": row.requirement,
        "result": row.result,
        "verdict": row.verdict,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }
    result = clean_dto(payload)
    assert isinstance(result, dict)
    return result
