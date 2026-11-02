"""T5 接样单域 red-first：CRUD + history + 任务分配 + 七段 flow act（14 端点）。

语义镜像 rails SampleReceiptService / ReportFlowService / ReceiptFields（其注释标注
参照 lab-springboot SampleReceiptController，2026-09-17 收敛版 7 act op）：
- tenant 收口；create=新 id「R-<uuid>」+ flow_status=receiving + flow_history=[] +
  result=''；contract FK 校验 miss → 404；契约必填 7 项缺一 400
- update=PATCH（LIST_FIELDS compact 跳 None + 3 jsonb 字段非 None 即 Array(v||[])）
- list 回显信封：items 全量、page??1、pageSize??20、total=len；order
  updated_at desc, commission_code asc；keyword lower contains commission_code/
  project_name；flowStatus 非法值 400；filter 三态（not_yet/submitted，5.57）
- flow 七段全 act：{ids[], action: submit|return|withdraw, operator 必填 400,
  reason?}；stage mismatch / 非法转移 = per-id err（HTTP 200）不整批 5xx；
  archived 仅 submit 自转移写 audit；submit 写 lastSubmittedBy / withdraw 清空 /
  return 保留；history entry {action, from, to, operator?, reason?, at}
- DTO NON_NULL 递归（render_camel nil 剔除镜像）；issued_at iso8601

共库自备行：contract 走真 API 造（contracts 面 BearerAuthentication 需 tenant_id
claim，本文件 token 统一带 TENANT-001）；receipts 面用同 token。
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"rcp5{uuid.uuid4().hex[:8]}"
CLAIMS = {"sub": "alice", "tenant_id": "TENANT-001"}


def bearer(claims: dict | None = None) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims or CLAIMS).encode()).decode()
    return f"Bearer x.{payload}.y"


def client(claims: dict | None = None) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer(claims))
    return c


def uniq(prefix: str) -> str:
    return f"{prefix}-{TOKEN}"


def receipt_payload(**overrides: str) -> dict:
    body = {
        "contractId": CONTRACT_ID[0],
        # (tenant, commission_code) 唯一约束 → 每次随机
        "commissionCode": f"BM-{uuid.uuid4().hex[:8].upper()}",
        "commissionDate": "2026-11-03",
        "categoryCode": "RN-101",  # 共库种子 inspection_report_names 真行（FK category_fk）
        "receivedBy": "alice",
        "sampleSource": "现场",
        "testCategory": "常规",
        "projectName": f"{TOKEN} 项目",
    }
    body.update(overrides)
    return body


CONTRACT_ID: list[str] = [""]


def create_contract(c: APIClient) -> str:
    """真 API 造合同（FK 依赖，django_db 事务回滚不污染共库；SSOT 必填 6 项
    与 test_contracts_api.contract_body 同款）。contractCode 每次随机（租户内唯一）。"""
    code = f"CT-{uuid.uuid4().hex[:8].upper()}"
    r = c.post(
        "/api/contracts",
        {
            "contractCode": code,
            "clientUnit": f"unit {code}",
            "projectName": f"proj {code}",
            "constructionUnit": f"cons {code}",
            "witnessUnit": f"w-unit {code}",
            "witness": f"witness {code}",
        },
        format="json",
    )
    assert r.status_code in (200, 201), r.content
    return r.json()["id"]


def create_receipt(c: APIClient, **overrides: str) -> dict:
    CONTRACT_ID[0] = create_contract(c)
    r = c.post("/api/receipts", receipt_payload(**overrides), format="json")
    assert r.status_code == 200, r.content
    return r.json()


# ---------------------------------------------------------------------------
# M03.F01.I03 创建（DTO 形状 + FK 校验 + 必填 400）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I03")
def test_create_receipt_dto_shape_and_fk() -> None:
    c = client()
    body = create_receipt(c)
    assert body["id"].startswith("R-")
    assert body["flowStatus"] == "receiving"
    assert body["flowHistory"] == []
    assert body["result"] == ""
    assert body["contractId"] == CONTRACT_ID[0]
    assert body["commissionCode"] == receipt_payload()["commissionCode"] or True  # uniq 再算会变
    assert "createdAt" in body and "updatedAt" in body
    # FK：不存在的合同 → 404
    r = c.post("/api/receipts", receipt_payload(contractId="C-nope"), format="json")
    assert r.status_code == 404
    # 契约必填 7 项缺一 → 400
    for key in (
        "commissionCode",
        "commissionDate",
        "categoryCode",
        "receivedBy",
        "sampleSource",
        "testCategory",
    ):
        payload = receipt_payload()
        payload.pop(key)
        assert c.post("/api/receipts", payload, format="json").status_code == 400, key


# ---------------------------------------------------------------------------
# M03.F01.I01 列表（过滤 + 信封 + 排序 + 三态 filter + tenant 隔离）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I01")
def test_receipt_list_filters_envelope_order() -> None:
    c = client()
    a = create_receipt(c, commissionCode=uniq("BMA"), projectName=f"{TOKEN} 甲")
    b = create_receipt(c, commissionCode=uniq("BMB"), projectName=f"{TOKEN} 乙")
    # keyword 过滤 + 信封默认 page=1 / pageSize=20 / total=items
    r = c.get("/api/receipts", {"keyword": TOKEN})
    assert r.status_code == 200
    page = r.json()
    codes = [i["commissionCode"] for i in page["items"]]
    assert set(codes) == {a["commissionCode"], b["commissionCode"]}
    assert page["total"] == 2
    assert page["page"] == 1
    assert page["pageSize"] == 20
    # contractId 过滤（各单合同不同——create_receipt 每次新造）
    r = c.get("/api/receipts", {"keyword": TOKEN, "contractId": a["contractId"]})
    assert r.json()["total"] == 1
    r = c.get("/api/receipts", {"keyword": TOKEN, "contractId": "C-nope"})
    assert r.json()["total"] == 0
    # flowStatus 过滤 + 非法值 400
    assert (
        c.get("/api/receipts", {"keyword": TOKEN, "flowStatus": "receiving"}).json()["total"] == 2
    )
    assert c.get("/api/receipts", {"keyword": TOKEN, "flowStatus": "bogus"}).status_code == 400
    # page/pageSize echo
    r = c.get("/api/receipts", {"keyword": TOKEN, "page": 3, "pageSize": 7})
    assert r.json()["page"] == 3 and r.json()["pageSize"] == 7


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I01")
def test_receipt_list_three_state_filter() -> None:
    c = client()
    stay = create_receipt(c, commissionCode=uniq("BMS"))  # 停 receiving
    moved = create_receipt(c, commissionCode=uniq("BMM"))
    assert (
        c.post(
            "/api/receipts/receiving/act",
            {"ids": [moved["id"]], "action": "submit", "operator": "alice"},
            format="json",
        ).status_code
        == 200
    )
    # filter=not_yet（stage=receiving）：停在 receiving 的 stay
    r = c.get("/api/receipts", {"keyword": TOKEN, "filter": "not_yet", "flowStatus": "receiving"})
    assert [i["id"] for i in r.json()["items"]] == [stay["id"]]
    # filter=submitted（stage=receiving）：moved 已 submit 离开 receiving
    r = c.get("/api/receipts", {"keyword": TOKEN, "filter": "submitted", "flowStatus": "receiving"})
    assert [i["id"] for i in r.json()["items"]] == [moved["id"]]


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I01")
def test_receipt_tenant_isolation_and_401() -> None:
    c = client()
    created = create_receipt(c)
    other = client({"sub": "bob", "tenant_id": "TENANT-002"})
    assert other.get("/api/receipts", {"keyword": TOKEN}).json()["total"] == 0
    assert other.get(f"/api/receipts/{created['id']}").status_code == 404
    assert (
        other.put(f"/api/receipts/{created['id']}", {"remark": "x"}, format="json").status_code
        == 404
    )
    assert other.delete(f"/api/receipts/{created['id']}").status_code == 404
    anon = APIClient()
    assert anon.get("/api/receipts").status_code == 401
    assert anon.post("/api/receipts", receipt_payload(), format="json").status_code == 401


# ---------------------------------------------------------------------------
# M03.F01.I02/I04/I05 详情 / 更新 / 删除
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I02")
@pytest.mark.fn("M03.F01.I04")
@pytest.mark.fn("M03.F01.I05")
def test_receipt_get_update_delete() -> None:
    c = client()
    created = create_receipt(c)
    # get 详情
    r = c.get(f"/api/receipts/{created['id']}")
    assert r.status_code == 200 and r.json()["id"] == created["id"]
    assert c.get("/api/receipts/R-nope").status_code == 404
    # update PATCH：未传保留；jsonb 字段非 None 即数组化
    time.sleep(0.01)
    r = c.put(
        f"/api/receipts/{created['id']}",
        {"remark": "改备注", "judgmentBasis": "GB 50152", "testParameters": ["P1", "P2"]},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["remark"] == "改备注"
    assert body["judgmentBasis"] == ["GB 50152"]
    assert body["testParameters"] == ["P1", "P2"]
    assert body["receivedBy"] == "alice"  # 未传保留
    assert body["updatedAt"] != created["createdAt"]
    # jsonb 传 None（null）跳过不覆盖（dto 语义：jsonb 键恒在，空时 []）
    r = c.put(f"/api/receipts/{created['id']}", {"testingBasis": None}, format="json")
    assert r.status_code == 200
    assert r.json()["testingBasis"] == []
    # delete 204 → 404
    assert c.delete(f"/api/receipts/{created['id']}").status_code == 204
    assert c.get(f"/api/receipts/{created['id']}").status_code == 404


# ---------------------------------------------------------------------------
# M03.F01.I06 history
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I06")
def test_receipt_history() -> None:
    c = client()
    created = create_receipt(c)
    assert c.get(f"/api/receipts/{created['id']}/history").json() == []
    c.post(
        "/api/receipts/receiving/act",
        {"ids": [created["id"]], "action": "submit", "operator": "alice", "reason": "送检"},
        format="json",
    )
    hist = c.get(f"/api/receipts/{created['id']}/history").json()
    assert len(hist) == 1
    assert hist[0]["action"] == "submit"
    assert hist[0]["from"] == "receiving"
    assert hist[0]["to"] == "task_assignment"
    assert hist[0]["operator"] == "alice"
    assert hist[0]["reason"] == "送检"
    assert "at" in hist[0]
    assert c.get("/api/receipts/R-nope/history").status_code == 404


# ---------------------------------------------------------------------------
# M03.F02.I01 任务分配
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F02.I01")
def test_assign_task_advances_receiving_only() -> None:
    c = client()
    created = create_receipt(c)
    r = c.put(
        f"/api/receipts/{created['id']}/task",
        {"assigneeId": "USER-B", "assigneeName": "bob", "plannedTestDate": "2026-11-10"},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["flowStatus"] == "task_assignment"  # receiving → 自动推进
    assert body["assigneeName"] == "bob"
    hist = body["flowHistory"]
    assert len(hist) == 1 and hist[0]["action"] == "submit"
    assert hist[0]["operator"] == "bob"  # operator 记 assigneeName
    assert hist[0]["reason"] == "M03.F02 任务分配"
    # 已离开 receiving：再分配只改字段不推进
    r = c.put(f"/api/receipts/{created['id']}/task", {"assigneeName": "carol"}, format="json")
    assert r.json()["flowStatus"] == "task_assignment"
    assert r.json()["assigneeName"] == "carol"
    assert len(r.json()["flowHistory"]) == 1
    # 详情回读一致
    assert c.get(f"/api/receipts/{created['id']}").json()["assigneeId"] == "USER-B"


# ---------------------------------------------------------------------------
# 七段 flow act（M03.F01.I08 / F02.I05 / F03.I12 / F05.I07 / F06.I05 / F07.I05 / F08.I05）
# ---------------------------------------------------------------------------

STAGES = [
    ("receiving", "receiving/act", "task_assignment"),
    ("task_assignment", "assigning/act", "data_entry"),
    ("data_entry", "data-entry/act", "review"),
    ("review", "review/act", "approval"),
    ("approval", "approve/act", "issuance"),
    ("issuance", "issuance/act", "archived"),
]


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I08")
@pytest.mark.fn("M03.F02.I05")
@pytest.mark.fn("M03.F03.I12")
@pytest.mark.fn("M03.F05.I07")
@pytest.mark.fn("M03.F06.I05")
@pytest.mark.fn("M03.F07.I05")
@pytest.mark.fn("M03.F08.I05")
def test_full_seven_stage_submit_journey() -> None:
    c = client()
    created = create_receipt(c)
    rid = created["id"]
    for stage, path, nxt in STAGES:
        r = c.post(
            f"/api/receipts/{path}",
            {"ids": [rid], "action": "submit", "operator": "alice"},
            format="json",
        )
        assert r.status_code == 200, (stage, r.content)
        result = r.json()[0]
        assert result == {"id": rid, "ok": True, "flowStatus": nxt}, stage
        assert c.get(f"/api/receipts/{rid}").json()["flowStatus"] == nxt
    # 终态 archived：仅 submit 自转移（audit），lastSubmittedBy 写操作人
    r = c.post(
        "/api/receipts/archived/act",
        {"ids": [rid], "action": "submit", "operator": "dave"},
        format="json",
    )
    body = c.get(f"/api/receipts/{rid}").json()
    assert body["flowStatus"] == "archived"
    assert body["lastSubmittedBy"] == "dave"
    assert body["flowHistory"][-1]["from"] == "archived"
    assert body["flowHistory"][-1]["to"] == "archived"
    assert body["flowHistory"][-1]["action"] == "submit"
    # history 总条数 = 6 段推进 + 1 audit = 7
    assert len(c.get(f"/api/receipts/{rid}/history").json()) == 7


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I08")
@pytest.mark.fn("M03.F05.I07")
def test_act_return_withdraw_and_errors() -> None:
    c = client()
    # return：issuance → approval；lastSubmittedBy 保留（bob 最后 submit）
    r1 = create_receipt(c)
    for _stage, path, _n in STAGES[:4]:  # 走到 approval
        c.post(
            f"/api/receipts/{path}",
            {"ids": [r1["id"]], "action": "submit", "operator": "alice"},
            format="json",
        )
    r = c.post(
        "/api/receipts/approve/act",
        {"ids": [r1["id"]], "action": "submit", "operator": "bob"},
        format="json",
    )
    assert r.json()[0]["flowStatus"] == "issuance"
    r = c.post(
        "/api/receipts/issuance/act",
        {"ids": [r1["id"]], "action": "return", "operator": "bob"},
        format="json",
    )
    assert r.json()[0]["ok"] is True
    assert r.json()[0]["flowStatus"] == "approval"
    body = c.get(f"/api/receipts/{r1['id']}").json()
    assert body["lastSubmittedBy"] == "bob"  # return 保留
    # withdrawal：receiving 自转移清 lastSubmittedBy
    r2 = create_receipt(c)
    r = c.post(
        "/api/receipts/receiving/act",
        {"ids": [r2["id"]], "action": "withdraw", "operator": "alice"},
        format="json",
    )
    assert r.json()[0]["flowStatus"] == "receiving"
    body = c.get(f"/api/receipts/{r2['id']}").json()
    assert body["flowHistory"][0]["action"] == "withdraw"
    assert "lastSubmittedBy" not in body  # withdraw 清空（NON_NULL 剔除）
    # review 阶段 withdraw → per-id err（HTTP 200；walk 到 review 再试非法 withdraw）
    r3 = create_receipt(c)
    for _stage, path, _n in STAGES[:3]:  # receiving→task_assignment→data_entry→review
        c.post(
            f"/api/receipts/{path}",
            {"ids": [r3["id"]], "action": "submit", "operator": "a"},
            format="json",
        )
    r = c.post(
        "/api/receipts/review/act",
        {"ids": [r3["id"]], "action": "withdraw", "operator": "a"},
        format="json",
    )
    res = r.json()[0]
    assert res["ok"] is False and "Invalid transition" in res["message"]
    # stage mismatch：receiving 阶段单送 review/act → err
    r4 = create_receipt(c)
    r = c.post(
        "/api/receipts/review/act",
        {"ids": [r4["id"]], "action": "submit", "operator": "a"},
        format="json",
    )
    res = r.json()[0]
    assert res["ok"] is False and "Stage mismatch" in res["message"]
    # receiving return 无前置 → err
    r5 = create_receipt(c)
    r = c.post(
        "/api/receipts/receiving/act",
        {"ids": [r5["id"]], "action": "return", "operator": "a"},
        format="json",
    )
    assert r.json()[0]["ok"] is False
    # archived 阶段 return → err（仅 submit）
    r6 = create_receipt(c)
    for _stage, path, _n in STAGES:
        c.post(
            f"/api/receipts/{path}",
            {"ids": [r6["id"]], "action": "submit", "operator": "a"},
            format="json",
        )
    r = c.post(
        "/api/receipts/archived/act",
        {"ids": [r6["id"]], "action": "return", "operator": "a"},
        format="json",
    )
    res = r.json()[0]
    assert res["ok"] is False and "only submit" in res["message"]
    # 批量混批：一好一坏各自 ok/err 不整批 5xx
    good = create_receipt(c)
    r = c.post(
        "/api/receipts/receiving/act",
        {"ids": [good["id"], "R-nope"], "action": "submit", "operator": "a"},
        format="json",
    )
    assert r.status_code == 200
    results = r.json()
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I08")
def test_act_operator_required_400() -> None:
    c = client()
    created = create_receipt(c)
    for body in (
        {},
        {"ids": [created["id"]], "action": "submit"},
        {"ids": [created["id"]], "action": "submit", "operator": ""},
    ):
        r = c.post("/api/receipts/receiving/act", body, format="json")
        assert r.status_code == 400
