"""T10 报告汇总 + 仪表盘统计 red-first：GET /api/summary + /api/summary/stats +
_frontend-bind/snapshot 占位端点。

语义镜像 rails SummaryService / MaterialRates（lab-springboot SummaryController
镜像；tenant 从 claim 取）：
- report_summary：tenant + categoryCode（'ALL'/缺省 = 不过滤）+ dateFrom/dateTo
  （commission_date 字典序 = 日期序）；order commission_date desc, commission_code
  asc；输出 {summaryName, columns(6 固定), rows[{commissionCode, categoryCode,
  projectName, flowStatus, result, reportCode}]}（nil → "" to_s 镜像）
- dashboard_stats：wire 键直出不走 camel（funnelByStage 的 pending_collect 是
  openapi 生成名）：contractCount/receiptCount/sampleCount + reportCountByStatus
  3 桶（draft=receiving+task+data_entry / reviewing=review+approval /
  issued=issuance+archived）+ pendingTaskCount + todayTestCount（created_at 或
  test_start_date 以今日 UTC 前缀）+ qualifiedRateByMaterial（码表 summaryName
  关键词归类 concrete/rebar/sand，rate 三位小数）+ reportOutputByStatus +
  funnelByStage 6 段（testing/reporting 按 data_entry 是否已有 report_code 拆分）
- _frontend-bind/snapshot：生成器 DTO 占位端点（rails/go 同款裁定）：挂认证，
  登录后 404 NOT_FOUND，匿名 401

共库自备行：contract/receipt 走真 API 造（T5 同款），django_db 事务回滚不污染。
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"sum10{uuid.uuid4().hex[:6]}"
CLAIMS = {"sub": "alice", "tenant_id": "TENANT-001"}


def bearer(claims: dict | None = None) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims or CLAIMS).encode()).decode()
    return f"Bearer x.{payload}.y"


def client(claims: dict | None = None) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer(claims))
    return c


def create_contract(c: APIClient) -> str:
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


def create_receipt(c: APIClient, contract_id: str, **overrides: str) -> dict:
    body = {
        "contractId": contract_id,
        "commissionCode": f"BM-{uuid.uuid4().hex[:8].upper()}",
        "commissionDate": "2026-11-03",
        "categoryCode": "RN-101",  # 共库种子 inspection_report_names 真行（FK）
        "receivedBy": "alice",
        "sampleSource": "现场",
        "testCategory": "常规",
        "projectName": f"{TOKEN} 项目",
    }
    body.update(overrides)
    r = c.post("/api/receipts", body, format="json")
    assert r.status_code == 200, r.content
    return r.json()


@pytest.mark.django_db
@pytest.mark.fn("M05.F01.I01")
def test_report_summary_category_date_rows() -> None:
    c = client()
    contract_id = create_contract(c)
    a = create_receipt(c, contract_id, commissionDate="2026-11-01")
    b = create_receipt(c, contract_id, commissionDate="2026-11-02")
    r = c.get("/api/summary", {"categoryCode": "RN-101"})
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["summaryName"] == "报告汇总（RN-101）"
    assert len(body["columns"]) == 6
    assert body["columns"][0] == {"key": "commissionCode", "label": "委托编号"}
    codes = [
        row["commissionCode"] for row in body["rows"] if row["commissionCode"].startswith("BM-")
    ]
    assert set(codes) >= {a["commissionCode"], b["commissionCode"]}
    # commission_date desc：11-02 在前
    assert codes.index(b["commissionCode"]) < codes.index(a["commissionCode"])
    row = next(row for row in body["rows"] if row["commissionCode"] == a["commissionCode"])
    assert row["projectName"] == f"{TOKEN} 项目"
    assert row["flowStatus"] == "receiving"
    assert row["result"] == "" and row["reportCode"] == ""  # nil → "" to_s 镜像
    # dateFrom/dateTo 字典序过滤
    r = c.get("/api/summary", {"categoryCode": "RN-101", "dateFrom": "2026-11-02"})
    codes = [row["commissionCode"] for row in r.json()["rows"]]
    assert b["commissionCode"] in codes and a["commissionCode"] not in codes
    r = c.get(
        "/api/summary",
        {"categoryCode": "RN-101", "dateFrom": "2026-11-01", "dateTo": "2026-11-01"},
    )
    assert [row["commissionCode"] for row in r.json()["rows"]] == [a["commissionCode"]]
    # 无 categoryCode = ALL 不过滤（summaryName 回显 ALL）
    r = c.get("/api/summary", {})
    assert r.json()["summaryName"] == "报告汇总（ALL）"
    assert APIClient().get("/api/summary").status_code == 401


@pytest.mark.django_db
@pytest.mark.fn("M05.F01.I06")
def test_dashboard_stats_wire_keys_buckets_funnel() -> None:
    c = client()
    contract_id = create_contract(c)
    create_receipt(c, contract_id)
    create_receipt(c, contract_id)
    r = c.get("/api/summary/stats")
    assert r.status_code == 200, r.content
    stats = r.json()
    # wire 键集直出（不走 camel：pending_collect 不得折叠成 pendingCollect）
    assert set(stats) == {
        "contractCount",
        "receiptCount",
        "sampleCount",
        "reportCountByStatus",
        "pendingTaskCount",
        "todayTestCount",
        "qualifiedRateByMaterial",
        "reportOutputByStatus",
        "funnelByStage",
    }
    assert stats["receiptCount"] >= 2
    assert stats["reportCountByStatus"]["draft"] >= 2  # receiving 入 draft 桶
    assert stats["pendingTaskCount"] == 0  # 新单全在 receiving，task+data_entry+review 桶为空
    assert stats["todayTestCount"] >= 2  # 新建单 created_at 是今天（UTC）
    assert stats["reportOutputByStatus"] == {
        "generated": 0,  # 无 report_code
        "pending": stats["reportCountByStatus"]["reviewing"],
        "issued": stats["reportCountByStatus"]["issued"],
    }
    funnel = stats["funnelByStage"]
    assert funnel["pending_collect"] >= 2  # receiving
    assert funnel["testing"] + funnel["reporting"] == 0  # data_entry 空
    assert set(funnel) == {
        "pending_collect",
        "received",
        "testing",
        "reporting",
        "reviewing",
        "issued",
    }
    rate = stats["qualifiedRateByMaterial"]
    # RN-101 码表 summaryName 关键词归类（concrete/rebar/sand 三键恒在，LinkedHashMap 序）
    assert set(rate) == {"concrete", "rebar", "sand"}
    assert set(rate["concrete"]) == {"total", "pass", "rate"}
    assert APIClient().get("/api/summary/stats").status_code == 401


@pytest.mark.django_db
@pytest.mark.fn("M03.F01.I02")
def test_frontend_bind_snapshot_placeholder() -> None:
    # 生成器 DTO 占位端点（go/rails 同款裁定）：挂认证，登录后 404；匿名 401
    assert client().get("/api/_frontend-bind/snapshot").status_code == 404
    body = APIClient().get("/api/_frontend-bind/snapshot")
    assert body.status_code == 401
