"""接样单域 service —— rails Receipts::SampleReceiptService 逐条镜像（其注释标注
参照 lab-springboot SampleReceiptService/SampleReceiptMapper，2026-09-17 收敛版）。

- tenant 收口；list 3 过滤（contractId/flowStatus 枚举 400/keyword lower contains
  commission_code/project_name）+ 5.57 三态 filter（not_yet/submitted）；order
  updated_at desc, commission_code asc
- create：contract FK 校验 miss → 404；id=「R-<uuid>」；flow_status=receiving、
  flow_history=[]、result=''、created_at/updated_at=now
- update：LIST_FIELDS 跳 None + JSON_LIST_FIELDS 非 None 即 Array(v||[])（jsonb
  三字段整体替换）+ updated_at 刷新
- assign_task：字段按需更新；仅 receiving 阶段推进 task_assignment 并写 history
  （action 字面量 "submit"、operator 记 assigneeName —— 参照实现）
- transition_to：状态迁移 + last_submitted_by 语义（5.69：submit 写操作人 /
  withdraw 清空 / return 保留）+ history 记 action 真值（5.75）
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from authn.errors import BadRequestError, NotFoundError
from entities.models import Contracts, SampleReceipts

# camel 命名业务字段（rails ReceiptFields LIST_FIELDS 镜像）：create/update 共用
LIST_FIELDS = (
    "commissionCode",
    "commissionDate",
    "commissionRegisterCode",
    "commissionRegisterDate",
    "categoryCode",
    "projectName",
    "clientUnit",
    "buildingUnit",
    "supervisorUnit",
    "constructionUnit",
    "witnessUnit",
    "samplingLocation",
    "witness",
    "witnessPhone",
    "inspector",
    "inspectorPhone",
    "receivedBy",
    "sampleSource",
    "testCategory",
    "testEnvironment",
    "mainEquipment",
    "testOperator",
    "testStartDate",
    "testEndDate",
    "originalRecordNo",
    "remark",
)
JSON_LIST_FIELDS = ("judgmentBasis", "testingBasis", "testParameters")
CREATE_REQUIRED = (
    "categoryCode",
    "commissionCode",
    "commissionDate",
    "contractId",
    "receivedBy",
    "sampleSource",
    "testCategory",
)

# 契约 enum FlowStatus（common.tsp，8 态）；非法 query 值 → 400（IAE 镜像）
FLOW_STATUSES = (
    "receiving",
    "task_assignment",
    "data_entry",
    "review",
    "approval",
    "issuance",
    "archived",
    "completed",
)


def _camel_to_attr(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def clean_dto(obj: Any) -> Any:
    """render_camel nil 剔除镜像（递归）：dict 剔 None 值、list 逐项、标量透传。"""
    if isinstance(obj, dict):
        return {k: clean_dto(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [clean_dto(v) for v in obj]
    return obj


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def list_receipts(
    tenant: str,
    contract_id: str | None,
    flow_status: str | None,
    keyword: str | None,
    filter_state: str | None,
) -> list[dict[str, Any]]:
    if flow_status is not None and flow_status not in FLOW_STATUSES:
        raise BadRequestError(f"Unexpected value '{flow_status}'")
    rows = list(
        SampleReceipts.objects.filter(tenant_id=tenant).order_by("-updated_at", "commission_code")
    )
    if contract_id:
        rows = [r for r in rows if r.contract_id == contract_id]
    if keyword:
        needle = keyword.lower()
        rows = [
            r
            for r in rows
            if needle in (r.commission_code or "").lower()
            or needle in (r.project_name or "").lower()
        ]
    if filter_state in ("not_yet", "submitted"):
        rows = [r for r in rows if _three_state_hit(r, flow_status or "", filter_state)]
    return [dto(r) for r in rows]


def _three_state_hit(row: SampleReceipts, stage: str, filter_state: str) -> bool:
    """5.57 三态谓词镜像（rails native SQL 的 python 等价；共库行数小）：
    not_yet = 停在本环节（无 stage 时=无流转记录新单）；
    submitted = 已从本环节 submit 至下一环节（无 stage 时=有流转且 lastSubmittedBy）。"""
    history = row.flow_history or []
    if filter_state == "not_yet":
        if stage:
            return row.flow_status == stage
        return len(history) == 0
    if stage:
        return row.flow_status != stage and any(
            h.get("action") == "submit" and h.get("from") == stage for h in history
        )
    return len(history) > 0 and bool(row.last_submitted_by)


def find_scoped(tenant: str, receipt_id: str) -> SampleReceipts:
    row = SampleReceipts.objects.filter(id=receipt_id).first()
    if row is None or row.tenant_id != tenant:
        raise NotFoundError(f"Receipt not found: {receipt_id}")
    return row


def get(tenant: str, receipt_id: str) -> dict[str, Any]:
    return dto(find_scoped(tenant, receipt_id))


def history(tenant: str, receipt_id: str) -> list[dict[str, Any]]:
    return find_scoped(tenant, receipt_id).flow_history or []


def create(tenant: str, body: dict[str, Any]) -> dict[str, Any]:
    missing = [f for f in CREATE_REQUIRED if not str(body.get(f) or "").strip()]
    if missing:
        raise BadRequestError(" / ".join(CREATE_REQUIRED) + " are required")
    contract_id = body.get("contractId")
    if not Contracts.objects.filter(id=contract_id, tenant_id=tenant).exists():
        raise NotFoundError(f"Contract not found: {contract_id}")
    now = now_iso()
    values: dict[str, Any] = {
        "id": f"R-{uuid.uuid4()}",
        "contract_id": contract_id,
        "tenant_id": tenant,
        "flow_status": "receiving",
        "flow_history": [],
        "result": "",
        "created_at": now,
        "updated_at": now,
    }
    for field in LIST_FIELDS:
        values[_camel_to_attr(field)] = body.get(field)
    row = SampleReceipts.objects.create(**values)
    return dto(row)


def update(tenant: str, receipt_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = find_scoped(tenant, receipt_id)
    for field in LIST_FIELDS:
        value = body.get(field)
        if value is not None:
            setattr(row, _camel_to_attr(field), value)
    for field in JSON_LIST_FIELDS:
        value = body.get(field)
        if value is not None:
            # Array(v||[]) 镜像：数组原样、标量包单元素数组（非 list(str) 逐字拆）
            normalized = value if isinstance(value, list) else [value]
            setattr(row, _camel_to_attr(field), normalized)
    row.updated_at = now_iso()
    row.save()
    return dto(row)


def delete(tenant: str, receipt_id: str) -> None:
    find_scoped(tenant, receipt_id).delete()


def assign_task(tenant: str, receipt_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """M03.F02 任务分配镜像：字段按需更新；仅 receiving 阶段推进 task_assignment
    并写 history（operator 记 assigneeName）。"""
    row = find_scoped(tenant, receipt_id)
    for field in ("assigneeId", "assigneeName", "plannedTestDate"):
        value = body.get(field)
        if value is not None:
            setattr(row, _camel_to_attr(field), value)
    if row.flow_status == "receiving":
        row.flow_status = "task_assignment"
        append_history(
            row,
            action="submit",
            operator=body.get("assigneeName"),
            **{"from": "receiving", "to": "task_assignment"},
            reason="M03.F02 任务分配",
        )
    row.updated_at = now_iso()
    row.save()
    return dto(row)


def transition_to(
    tenant: str,
    receipt_id: str,
    *,
    frm: str,
    to: str,
    action: str,
    operator: str | None,
    reason: str | None,
) -> dict[str, Any]:
    row = find_scoped(tenant, receipt_id)
    if row.flow_status != frm:
        raise BadRequestError(
            f"Receipt {receipt_id} not in expected stage {frm} but {row.flow_status}"
        )
    row.flow_status = to
    if action == "submit":
        row.last_submitted_by = operator
    elif action == "withdraw":
        row.last_submitted_by = None
    append_history(row, action=action, operator=operator, **{"from": frm, "to": to}, reason=reason)
    row.updated_at = now_iso()
    row.save()
    return dto(row)


def append_history(row: SampleReceipts, **entry: Any) -> None:
    """flow_history 追加（entry 键集 action/from/to/operator/reason + at）。"""
    record = dict(entry)
    record["at"] = now_iso()
    row.flow_history = list(row.flow_history or []) + [record]


def dto(row: SampleReceipts) -> dict[str, Any]:
    """ReceiptFields#dto 镜像（camelCase）；jsonb 字段 ||[] 恒在；NON_NULL 剔 None。"""
    payload: dict[str, Any] = {
        "id": row.id,
        "contractId": row.contract_id,
        "commissionCode": row.commission_code,
        "commissionDate": row.commission_date,
        "commissionRegisterCode": row.commission_register_code,
        "commissionRegisterDate": row.commission_register_date,
        "categoryCode": row.category_code,
        "projectName": row.project_name,
        "clientUnit": row.client_unit,
        "buildingUnit": row.building_unit,
        "supervisorUnit": row.supervisor_unit,
        "constructionUnit": row.construction_unit,
        "witnessUnit": row.witness_unit,
        "samplingLocation": row.sampling_location,
        "witness": row.witness,
        "witnessPhone": row.witness_phone,
        "inspector": row.inspector,
        "inspectorPhone": row.inspector_phone,
        "receivedBy": row.received_by,
        "sampleSource": row.sample_source,
        "testCategory": row.test_category,
        "testEnvironment": row.test_environment,
        "mainEquipment": row.main_equipment,
        "testOperator": row.test_operator,
        "testStartDate": row.test_start_date,
        "testEndDate": row.test_end_date,
        "originalRecordNo": row.original_record_no,
        "remark": row.remark,
        "judgmentBasis": row.judgment_basis or [],
        "testingBasis": row.testing_basis or [],
        "testParameters": row.test_parameters or [],
        "flowStatus": row.flow_status,
        "flowHistory": row.flow_history or [],
        "lastSubmittedBy": row.last_submitted_by,
        "assigneeId": row.assignee_id,
        "assigneeName": row.assignee_name,
        "plannedTestDate": row.planned_test_date,
        "reportCode": row.report_code,
        "reportDate": row.report_date,
        "conclusion": row.conclusion,
        "result": row.result,
        "issuedAt": row.issued_at.isoformat() if row.issued_at else None,
        "tenantId": row.tenant_id,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }
    result = clean_dto(payload)
    assert isinstance(result, dict)
    return result
