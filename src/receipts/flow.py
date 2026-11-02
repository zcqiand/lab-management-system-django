"""报告流程状态机 M03.F01-F08 —— rails Receipts::ReportFlowService 逐条镜像
（lab-springboot ReportFlowService 镜像，2026-09-17 收敛版：POST
/receipts/<stage>/act，body.action={submit|return|withdraw}）。

action 范围因 stage 而异：
- receiving/assigning(task_assignment)/data-entry：{submit, return, withdraw}
- review/approve(approval)/issuance：{submit, return}
- archived：仅 submit（终态自转移，写 history 当 audit，语义按 submit 走 5.69）
WITHDRAW 仅在 receiving 阶段自转移。per-id try/except：单条失败出 err 结果不整批 5xx。
"""

from __future__ import annotations

from typing import Any

SUBMIT_NEXT = {
    "receiving": "task_assignment",
    "task_assignment": "data_entry",
    "data_entry": "review",
    "review": "approval",
    "approval": "issuance",
    "issuance": "archived",
}
RETURN_PREV = {
    "task_assignment": "receiving",
    "data_entry": "task_assignment",
    "review": "data_entry",
    "approval": "review",
    "issuance": "approval",
    "archived": "issuance",
}


def require_operator(body: dict[str, Any]) -> str:
    """5.75 operator 契约必填（SSOT = lab-nextjs act-route.ts）：缺失与空串都 400，
    校验先于 per-id 循环（整批拒）。"""
    operator = body.get("operator")
    if operator is None or operator == "":
        from authn.errors import BadRequestError

        raise BadRequestError("operator is required")
    return str(operator)


def _target_of(current: str, action: str) -> str | None:
    if action == "submit":
        return SUBMIT_NEXT.get(current)
    if action == "return":
        return RETURN_PREV.get(current)
    if action == "withdraw":
        return current if current == "receiving" else None
    return None


def _ok(receipt_id: str, flow_status: str) -> dict[str, Any]:
    return {"id": receipt_id, "ok": True, "flowStatus": flow_status}


def _err(receipt_id: str, message: str) -> dict[str, Any]:
    return {"id": receipt_id, "ok": False, "message": message}


def act(stage: str, body: dict[str, Any], service: Any, tenant: str) -> list[dict[str, Any]]:
    """批量 act：operator 整批校验后 per-id 推进；结果 FlowActionResult[]。"""
    operator = require_operator(body)
    reason = body.get("reason")
    action = body.get("action")
    results: list[dict[str, Any]] = []
    for receipt_id in body.get("ids") or []:
        results.append(_act_one(stage, receipt_id, action, operator, reason, service, tenant))
    return results


def _act_one(
    stage: str,
    receipt_id: str,
    action: Any,
    operator: str,
    reason: str | None,
    service: Any,
    tenant: str,
) -> dict[str, Any]:
    try:
        current = service.get(tenant, receipt_id)["flowStatus"]
        if stage == "archived":
            return _act_archived_one(receipt_id, action, operator, reason, service, tenant)
        if current != stage:
            return _err(receipt_id, f"Stage mismatch: requires {stage} but is {current}")
        target = _target_of(current, str(action) if action is not None else "")
        if target is None:
            return _err(receipt_id, f"Invalid transition from {current} with {action}")
        service.transition_to(
            tenant,
            receipt_id,
            frm=current,
            to=target,
            action=str(action),
            operator=operator,
            reason=reason,
        )
        return _ok(receipt_id, target)
    except Exception as exc:  # noqa: BLE001 —— per-id err 不整批 5xx（rails rescue StandardError 同形）
        return _err(receipt_id, str(exc))


def _act_archived_one(
    receipt_id: str,
    action: Any,
    operator: str,
    reason: str | None,
    service: Any,
    tenant: str,
) -> dict[str, Any]:
    """archived 终态：仅 submit；自转移写 audit（reason 缺省
    "archived: post-archive audit"，语义按 submit —— lastSubmittedBy 写操作人）。"""
    current = service.get(tenant, receipt_id)["flowStatus"]
    if current != "archived":
        return _err(receipt_id, f"Stage mismatch: requires archived but is {current}")
    if action != "submit":
        return _err(
            receipt_id,
            f"Action not allowed: archived accepts only submit but got {action}",
        )
    service.transition_to(
        tenant,
        receipt_id,
        frm="archived",
        to="archived",
        action="submit",
        operator=operator,
        reason=reason or "archived: post-archive audit",
    )
    return _ok(receipt_id, "archived")
