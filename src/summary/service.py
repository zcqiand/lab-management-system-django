"""M05 报告汇总 + 仪表盘统计 service —— rails SummaryService / MaterialRates
逐条镜像（lab-springboot SummaryService 镜像；tenant 从 claim 取）。

- report_summary：tenant + categoryCode（'ALL'/缺省 = 不过滤）+ dateFrom/dateTo
  （commission_date 字典序 = 日期序，null 视作无界）；order commission_date desc,
  commission_code asc；nil → "" to_s 镜像
- dashboard_stats：wire 键直出不走 camel（funnelByStage 的 pending_collect 是
  openapi 生成名，不得被 camelCase 折叠成 pendingCollect——rails 注记原样镜像）
- 「今天」与 created_at 戳同钟取 UTC（2026-10-21 SummaryApiTest 实证红：
  戳是 now_iso=UTC，比较基准取本地 Date.today 会在 UTC+8 00:00-08:00 把新单判成非当日）
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from entities.models import Contracts, InspectionReportNames, SampleReceipts, Samples
from receipts.service import clean_dto

CATEGORY_ALL = "ALL"

COLUMNS = [
    {"key": "commissionCode", "label": "委托编号"},
    {"key": "categoryCode", "label": "报告类别"},
    {"key": "projectName", "label": "工程名称"},
    {"key": "flowStatus", "label": "流程状态"},
    {"key": "result", "label": "结论"},
    {"key": "reportCode", "label": "报告编号"},
]

# summaryName → 材料类型映射（与 msw handlers-extra 同款语义，dict 保序=LinkedHashMap）
MATERIAL_KEYWORDS = {
    "concrete": ["混凝土", "水泥"],
    "rebar": ["钢筋", "钢材", "焊接", "机械连接", "连接"],
    "sand": ["砂", "碎（卵）石", "轻集料", "颗粒级配"],
}


def _category_of(category_code: str | None) -> str:
    return category_code if category_code else CATEGORY_ALL


def summary_scope(
    tenant: str, category_code: str | None, date_from: str | None, date_to: str | None
) -> list[SampleReceipts]:
    rows = list(
        SampleReceipts.objects.filter(tenant_id=tenant).order_by(
            "-commission_date", "commission_code"
        )
    )
    cat = _category_of(category_code)
    if cat != CATEGORY_ALL:
        rows = [r for r in rows if r.category_code == cat]
    if date_from:
        rows = [r for r in rows if (r.commission_date or "") >= date_from]
    if date_to:
        rows = [r for r in rows if (r.commission_date or "") <= date_to]
    return rows


def report_summary(
    tenant: str, category_code: str | None, date_from: str | None, date_to: str | None
) -> dict[str, Any]:
    rows = summary_scope(tenant, category_code, date_from, date_to)
    result = clean_dto(
        {
            "summaryName": f"报告汇总（{_category_of(category_code)}）",
            "columns": COLUMNS,
            "rows": [
                {
                    "commissionCode": r.commission_code or "",
                    "categoryCode": r.category_code or "",
                    "projectName": r.project_name or "",
                    "flowStatus": r.flow_status or "",
                    "result": r.result or "",
                    "reportCode": r.report_code or "",
                }
                for r in rows
            ],
        }
    )
    assert isinstance(result, dict)
    return result


# ---------------------------------------------------------------------------
# dashboard stats（wire 键直出）
# ---------------------------------------------------------------------------


def _bucket(counting: dict[str, list[SampleReceipts]], *stages: str) -> int:
    return sum(len(counting.get(s, [])) for s in stages)


def _material_of(category_code: str | None, summary_name_by_code: dict[str, str]) -> str | None:
    if category_code is None:
        return None
    summary_name = summary_name_by_code.get(category_code, "")
    for mat, keywords in MATERIAL_KEYWORDS.items():
        if any(kw in summary_name for kw in keywords):
            return mat
    return None


def _qualified_rate_by_material(
    receipts: list[SampleReceipts],
) -> dict[str, dict[str, float | int]]:
    summary_name_by_code = {
        rn.code: rn.summary_name or "" for rn in InspectionReportNames.objects.all()
    }
    total = {"concrete": 0, "rebar": 0, "sand": 0}
    passed = {"concrete": 0, "rebar": 0, "sand": 0}
    for r in receipts:
        mat = _material_of(r.category_code, summary_name_by_code)
        if mat is None:
            continue
        total[mat] += 1
        if r.result == "pass":
            passed[mat] += 1
    # rate 三位小数（ruby Float#round 半入镜像：int(x+0.5)，避开 python 银行家舍入）
    return {
        mat: {
            "total": t,
            "pass": passed[mat],
            "rate": (int(passed[mat] * 1000.0 / t + 0.5) / 1000.0) if t > 0 else 0.0,
        }
        for mat, t in total.items()
    }


def _today_test_count(receipts: list[SampleReceipts]) -> int:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return sum(
        1
        for r in receipts
        if (r.created_at or "").startswith(today) or (r.test_start_date or "").startswith(today)
    )


def dashboard_stats(tenant: str) -> dict[str, Any]:
    receipts = summary_scope(tenant, None, None, None)
    counting: dict[str, list[SampleReceipts]] = defaultdict(list)
    for r in receipts:
        counting[r.flow_status or ""].append(r)
    data_entry = counting.get("data_entry", [])
    return {
        "contractCount": Contracts.objects.filter(tenant_id=tenant).count(),
        "receiptCount": len(receipts),
        "sampleCount": Samples.objects.filter(tenant_id=tenant).count(),
        "reportCountByStatus": {
            "draft": _bucket(counting, "receiving", "task_assignment", "data_entry"),
            "reviewing": _bucket(counting, "review", "approval"),
            "issued": _bucket(counting, "issuance", "archived"),
        },
        "pendingTaskCount": _bucket(counting, "task_assignment", "data_entry", "review"),
        "todayTestCount": _today_test_count(receipts),
        "qualifiedRateByMaterial": _qualified_rate_by_material(receipts),
        "reportOutputByStatus": {
            "generated": sum(1 for r in receipts if r.report_code is not None),
            "pending": _bucket(counting, "review", "approval"),
            "issued": _bucket(counting, "issuance", "archived"),
        },
        "funnelByStage": {
            "pending_collect": _bucket(counting, "receiving"),
            "received": _bucket(counting, "task_assignment"),
            "testing": sum(1 for r in data_entry if r.report_code is None),
            "reporting": sum(1 for r in data_entry if r.report_code is not None),
            "reviewing": _bucket(counting, "review", "approval"),
            "issued": _bucket(counting, "issuance", "archived"),
        },
    }
