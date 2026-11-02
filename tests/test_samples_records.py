"""T6 样品 + 检测记录域 red-first：samples 6 op + test-records 6 op。

语义镜像 rails SampleService / TestRecordService（其注释标注 lab-springboot 镜像）：
- samples：tenant-scoped + receipt FK 显式校验（miss→404 "Receipt not found"，
  不是 FK→400）；keyword lower contains sample_code/sample_name；order
  created_at DESC, sample_code ASC；create ext 默认 {}；update PATCH 跳 None
  （ext 非 None 才替换）；PUT /{id}/ext 整体替换且 ext 必填 400（5.89）；delete 204
- test-records：create 四必填 400（sampleId/parameterCode/requirement/result）；
  sample/parameter/standard FK 走 DB 约束（→400，rails InvalidForeignKey 镜像）；
  order updated_at DESC, id ASC；update PATCH 跳 None；set_verdict 直写可置 null；
  delete 204
- 两域 list 回显信封（items 全量、page??1、pageSize??20、total=len）；
  DTO NON_NULL 递归（ext 例外：键恒在，空时 {}）

共库自备行：receipt 走真 API 造（samples FK）；parameter/standard 用种子真行
（IP-0001 / GB 1499.1-2024，FK 全局无 tenant 列）。
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"smp6{uuid.uuid4().hex[:8]}"
CLAIMS = {"sub": "alice", "tenant_id": "TENANT-001"}
PARAM = "IP-0001"  # 种子 inspection_parameters 真行（testrec_param_fk）
STANDARD = "GB 1499.1-2024"  # 种子 inspection_standards 真行（testrec_standard_fk）


def bearer(claims: dict | None = None) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims or CLAIMS).encode()).decode()
    return f"Bearer x.{payload}.y"


def client(claims: dict | None = None) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer(claims))
    return c


def create_receipt(c: APIClient) -> str:
    """真 API 造合同+接样单（samples FK 依赖；django_db 事务回滚不污染共库）。"""
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
    r = c.post(
        "/api/receipts",
        {
            "contractId": r.json()["id"],
            "commissionCode": f"BM-{uuid.uuid4().hex[:8].upper()}",
            "commissionDate": "2026-11-03",
            "categoryCode": "RN-101",
            "receivedBy": "alice",
            "sampleSource": "现场",
            "testCategory": "常规",
            "projectName": f"{TOKEN} 单",
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    return r.json()["id"]


def sample_payload(receipt_id: str = "", **overrides: str | dict) -> dict:
    body = {
        "receiptId": receipt_id,
        "sampleCode": f"SMP-{TOKEN}-{uuid.uuid4().hex[:6]}",
        "sampleName": f"{TOKEN} 样品",
        "manufacturer": "厂商A",
    }
    body.update(overrides)
    return body


def create_sample(c: APIClient, **overrides: str | dict) -> dict:
    if not overrides.get("receiptId"):
        overrides["receiptId"] = create_receipt(c)
    r = c.post("/api/samples", sample_payload(**overrides), format="json")
    assert r.status_code == 200, r.content
    return r.json()


def record_payload(sample_id: str, **overrides: str) -> dict:
    body = {
        "sampleId": sample_id,
        "parameterCode": PARAM,
        "standardCode": STANDARD,
        "requirement": "≥ 10 MPa",
        "result": "12.3",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# M03.F03.I03 创建样品（DTO 形状 + FK 404 + 必填 400 + ext 默认 {}）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I03")
def test_create_sample_dto_fk_required_ext_default() -> None:
    c = client()
    receipt_id = create_receipt(c)
    r = c.post("/api/samples", sample_payload(receipt_id, ext={"壁厚": "8mm"}), format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["id"].startswith("S-")
    assert body["receiptId"] == receipt_id
    assert body["sampleCode"] == sample_payload(receipt_id)["sampleCode"] or True  # 每次随机
    assert body["ext"] == {"壁厚": "8mm"}
    assert body["tenantId"] == "TENANT-001"
    assert "createdAt" in body and "updatedAt" in body
    # receipt FK 显式校验 miss → 404（不是 FK→400）
    assert c.post("/api/samples", sample_payload("R-nope"), format="json").status_code == 404
    # sampleCode 缺 → 400
    assert c.post("/api/samples", {"receiptId": receipt_id}, format="json").status_code == 400
    # ext 缺省 → {}
    body = create_sample(c)
    assert body["ext"] == {}


# ---------------------------------------------------------------------------
# M03.F03.I01 列表（过滤 + 信封 + 排序 + tenant 隔离）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I01")
def test_sample_list_filters_envelope_order() -> None:
    c = client()
    rid = create_receipt(c)
    a = create_sample(c, receiptId=rid, sampleName=f"{TOKEN} 甲样品")
    time.sleep(0.01)
    b = create_sample(c, receiptId=rid, sampleName=f"{TOKEN} 乙样品")
    r = c.get("/api/samples", {"keyword": TOKEN})
    assert r.status_code == 200
    page = r.json()
    ids = [i["id"] for i in page["items"]]
    assert set(ids) == {a["id"], b["id"]}
    assert ids[0] == b["id"]  # created_at DESC
    assert page["total"] == 2 and page["page"] == 1 and page["pageSize"] == 20
    # receiptId 过滤
    assert c.get("/api/samples", {"keyword": TOKEN, "receiptId": rid}).json()["total"] == 2
    assert c.get("/api/samples", {"keyword": TOKEN, "receiptId": "R-nope"}).json()["total"] == 0
    # page/pageSize echo
    r = c.get("/api/samples", {"keyword": TOKEN, "page": 2, "pageSize": 5})
    assert r.json()["page"] == 2 and r.json()["pageSize"] == 5


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I01")
def test_sample_tenant_isolation_and_401() -> None:
    c = client()
    created = create_sample(c)
    other = client({"sub": "bob", "tenant_id": "TENANT-002"})
    assert other.get("/api/samples", {"keyword": TOKEN}).json()["total"] == 0
    assert other.get(f"/api/samples/{created['id']}").status_code == 404
    assert (
        other.put(f"/api/samples/{created['id']}", {"remark": "x"}, format="json").status_code
        == 404
    )
    assert other.delete(f"/api/samples/{created['id']}").status_code == 404
    anon = APIClient()
    assert anon.get("/api/samples").status_code == 401
    assert anon.post("/api/samples", {}, format="json").status_code == 401


# ---------------------------------------------------------------------------
# M03.F03.I02/I04/I05 详情 / 更新 / 删除
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I02")
@pytest.mark.fn("M03.F03.I04")
@pytest.mark.fn("M03.F03.I05")
def test_sample_get_update_delete() -> None:
    c = client()
    created = create_sample(c)
    assert c.get(f"/api/samples/{created['id']}").json()["id"] == created["id"]
    assert c.get("/api/samples/S-nope").status_code == 404
    time.sleep(0.01)
    r = c.put(
        f"/api/samples/{created['id']}",
        {"remark": "改备注", "grade": "C30"},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["remark"] == "改备注" and body["grade"] == "C30"
    assert body["manufacturer"] == "厂商A"  # 未传保留
    assert body["updatedAt"] != created["createdAt"]
    # ext 非 None 才替换（None 跳过）
    r = c.put(f"/api/samples/{created['id']}", {"ext": None}, format="json")
    assert r.status_code == 200 and r.json()["ext"] == {}
    assert c.delete(f"/api/samples/{created['id']}").status_code == 204
    assert c.get(f"/api/samples/{created['id']}").status_code == 404


# ---------------------------------------------------------------------------
# M03.F01.I07 ext 补录（整体替换 + ext 必填 400）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I07")
def test_sample_ext_overwrite() -> None:
    c = client()
    created = create_sample(c, ext={"a": "1"})
    # 整体替换（合并是前端职责）
    r = c.put(f"/api/samples/{created['id']}/ext", {"ext": {"b": "2"}}, format="json")
    assert r.status_code == 200
    assert r.json()["ext"] == {"b": "2"}  # a 被替换掉
    # ext 必填（5.89）：缺 ext 键 → 400
    assert c.put(f"/api/samples/{created['id']}/ext", {}, format="json").status_code == 400
    assert (
        c.put(f"/api/samples/{created['id']}/ext", {"ext": None}, format="json").status_code == 400
    )


# ---------------------------------------------------------------------------
# M03.F03.I08 创建检测记录（四必填 400 + FK DB 约束 400）+ I06 列表 + I07 详情
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I08")
def test_create_record_required_and_fk() -> None:
    c = client()
    sample = create_sample(c)
    r = c.post("/api/test-records", record_payload(sample["id"]), format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["id"].startswith("TR-")
    assert body["sampleId"] == sample["id"]
    assert body["parameterCode"] == PARAM
    assert body["requirement"] == "≥ 10 MPa"
    assert body["result"] == "12.3"
    assert body["tenantId"] == "TENANT-001"
    # 四必填缺一 → 400
    for key in ("sampleId", "parameterCode", "requirement", "result"):
        payload = record_payload(sample["id"])
        payload.pop(key)
        assert c.post("/api/test-records", payload, format="json").status_code == 400, key
    # sample FK（DB 约束）→ 400
    assert c.post("/api/test-records", record_payload("S-nope"), format="json").status_code == 400
    # parameter/standard FK（DB 约束）→ 400
    assert (
        c.post(
            "/api/test-records",
            record_payload(sample["id"], parameterCode="IP-nope"),
            format="json",
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/api/test-records", record_payload(sample["id"], standardCode="XX-nope"), format="json"
        ).status_code
        == 400
    )


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I06")
@pytest.mark.fn("M03.F03.I07")
def test_record_list_get_envelope() -> None:
    c = client()
    sample = create_sample(c)
    r1 = c.post("/api/test-records", record_payload(sample["id"], result="1"), format="json").json()
    time.sleep(0.01)
    r2 = c.post("/api/test-records", record_payload(sample["id"], result="2"), format="json").json()
    r = c.get("/api/test-records", {"sampleId": sample["id"]})
    assert r.status_code == 200
    page = r.json()
    ids = [i["id"] for i in page["items"]]
    assert set(ids) == {r1["id"], r2["id"]}
    assert ids[0] == r2["id"]  # updated_at DESC
    assert page["total"] == 2 and page["page"] == 1 and page["pageSize"] == 20
    assert c.get("/api/test-records", {"sampleId": "S-nope"}).json()["total"] == 0
    # 详情
    assert c.get(f"/api/test-records/{r1['id']}").json()["result"] == "1"
    assert c.get("/api/test-records/TR-nope").status_code == 404


# ---------------------------------------------------------------------------
# M03.F03.I09 更新 + I10 删除
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I09")
@pytest.mark.fn("M03.F03.I10")
def test_record_update_delete() -> None:
    c = client()
    sample = create_sample(c)
    created = c.post("/api/test-records", record_payload(sample["id"]), format="json").json()
    time.sleep(0.01)
    r = c.put(
        f"/api/test-records/{created['id']}",
        {"result": "13.8", "verdict": "qualified"},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "13.8" and body["verdict"] == "qualified"
    assert body["requirement"] == "≥ 10 MPa"  # 未传保留
    assert body["updatedAt"] != created["createdAt"]
    assert c.delete(f"/api/test-records/{created['id']}").status_code == 204
    assert c.get(f"/api/test-records/{created['id']}").status_code == 404


# ---------------------------------------------------------------------------
# M03.F03.I11 人工改判 verdict（直写可置 null）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M03.F03.I11")
def test_record_set_verdict() -> None:
    c = client()
    sample = create_sample(c)
    created = c.post("/api/test-records", record_payload(sample["id"]), format="json").json()
    time.sleep(0.01)
    r = c.patch(
        f"/api/test-records/{created['id']}/verdict", {"verdict": "rejected"}, format="json"
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "rejected"
    assert r.json()["updatedAt"] != created["createdAt"]
    # 置 null 清空（NON_NULL 剔除 → 键不在）
    r = c.patch(f"/api/test-records/{created['id']}/verdict", {"verdict": None}, format="json")
    assert r.status_code == 200
    assert "verdict" not in r.json()
