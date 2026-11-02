"""M02.F01 合同管理首切片（REQ-2026-030，T-4）——I01-I05 行为单测。

契约 SSOT：shared emit openapi（scripts/gen-shared.sh 生成区）。
语义仲裁（docs/design/design-function-map.md「关键语义分叉」）：
  - 鉴权 decode-only（bearer 只解 payload 不验签，nextjs oracle bearer.ts）；
    401 信封 {code:UNAUTHORIZED, message:"tenant_id claim is required (ADR-0019)"}
  - 分页 1-based（CT contracts.test.ts T11 live 实证，page=1/pageSize=20 默认）
  - 列全 text，id/时间戳 app 侧生成（uuid4 + ISO NOW），status 字符串 active/archived
  - 租户身份只取 token 的 tenant_id claim（ADR-0019，body.tenantId 忽略）
测试库 = 家族 lab_test（shared seed：CONTRACT-001/002/003，租户随种子行），
写测试走 django_db 事务回滚，不污染共库。
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

import pytest
from rest_framework.test import APIClient

LIST_URL = "/api/contracts"
DEAD_ID = "00000000-0000-0000-0000-00000000dead"

# token 租户 claim 真源=shared 种子行（2026-11-02 5.129 同类第三处）：曾硬编码
# "TENANT-001"，tenant_key 收口批（2026-11-01）种子迁 acme 后 claim×行租户错位
# → 列表 total=0 → items[0] IndexError。种子不唯一则 fail-fast，禁回落字面量。
_seed_tenants = sorted(
    {
        row["tenant_id"]
        for row in json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "lab-management-system-shared"
                / "seeds"
                / "contracts.json"
            ).read_text(encoding="utf-8")
        )
    }
)
if len(_seed_tenants) != 1 or not _seed_tenants[0]:
    raise RuntimeError(
        f"fail-fast: seeds/contracts.json tenant_id 不唯一或为空（{_seed_tenants}）"
        "——token 租户 claim 无真源"
    )
TENANT = _seed_tenants[0]

# nextjs oracle Row 形状（drizzle select() 全列 → camelCase JSON，含 tenantId）
CONTRACT_FIELDS = {
    "id",
    "contractCode",
    "clientUnit",
    "projectName",
    "projectLocation",
    "constructionUnit",
    "inspectionSpecialtyCode",
    "buildingUnit",
    "supervisorUnit",
    "inspectionPerson",
    "inspectionPhone",
    "witnessUnit",
    "witness",
    "witnessPhone",
    "contactPerson",
    "contactPhone",
    "entrustedDate",
    "status",
    "createdAt",
    "updatedAt",
    "tenantId",
}


def bearer(tenant: str = TENANT, sub: str = "alice") -> str:
    """decode-only 假 token：header.payload.sig 三段，payload 只装 tenant_id claim。"""
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "tenant_id": tenant}).encode()
    ).decode()
    return f"Bearer x.{payload}.y"


def client(tenant: str | None = TENANT) -> APIClient:
    c = APIClient()
    if tenant is not None:
        c.credentials(HTTP_AUTHORIZATION=bearer(tenant))
    return c


def contract_body(code: str) -> dict[str, str]:
    """SSOT CreateContractRequest 必填 6 项（CT contracts.test.ts contractBody 同款）。"""
    return {
        "contractCode": code,
        "clientUnit": f"unit {code}",
        "projectName": f"proj {code}",
        "constructionUnit": f"cons {code}",
        "witnessUnit": f"w-unit {code}",
        "witness": f"witness {code}",
    }


def create_via_api(code: str | None = None, **extra: str) -> dict:
    """测试自备行（事务回滚不清库）：POST 走真路径，返回响应 body。"""
    payload = contract_body(code or f"DJ-{uuid.uuid4().hex[:8].upper()}")
    payload.update(extra)
    resp = client().post(LIST_URL, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


# ---------- I01 合同列表 ----------


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_no_token_401() -> None:
    resp = APIClient().get(LIST_URL)
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["message"] == "tenant_id claim is required (ADR-0019)"


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_token_without_tenant_claim_401() -> None:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "alice"}).encode()).decode()
    resp = APIClient().get(LIST_URL, HTTP_AUTHORIZATION=f"Bearer x.{payload}.y")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_garbage_token_401() -> None:
    resp = APIClient().get(LIST_URL, HTTP_AUTHORIZATION="Bearer not-a-token")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_200_default_pagination_1_based() -> None:
    from entities.models import Contracts as Contract

    resp = client().get(LIST_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"items", "page", "pageSize", "total"}
    # 1-based（CT T11 live 实证——saas 0 基是 saas 家族语义，lab 不随）
    assert body["page"] == 1
    assert body["pageSize"] == 20
    assert body["total"] == Contract.objects.filter(tenant_id=TENANT).count()
    assert len(body["items"]) == body["total"]
    assert set(body["items"][0]) == CONTRACT_FIELDS


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_page_slice() -> None:
    resp = client().get(LIST_URL, {"page": "2", "pageSize": "2"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 2
    assert body["pageSize"] == 2
    assert len(body["items"]) == body["total"] - 2


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_keyword_filter_contract_code_or_project_name() -> None:
    # seed：HT-2025-098 是唯一 HT-2025 前缀行
    resp = client().get(LIST_URL, {"keyword": "HT-2025"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["contractCode"] == "HT-2025-098"
    # keyword 也命中 projectName（ilike 二选一）
    seed = client().get(LIST_URL, {"keyword": "HT-2025-098"}).json()["items"][0]
    resp2 = client().get(LIST_URL, {"keyword": seed["projectName"]})
    assert resp2.json()["total"] == 1
    assert resp2.json()["items"][0]["id"] == seed["id"]


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_status_filter() -> None:
    resp = client().get(LIST_URL, {"status": "archived"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "archived"
    resp2 = client().get(LIST_URL, {"status": "active"})
    assert resp2.json()["total"] == 2


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I01")
def test_list_tenant_scoped_from_claim() -> None:
    resp = client(tenant="TENANT-OTHER").get(LIST_URL)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0  # seed 全单租户（真源见 TENANT 推导），别的租户看不到


# ---------- I03 创建合同 ----------
# （I03 测试排本段：create_via_api 是 I04/I05 夹具依赖，须先于它们可读）


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I03")
def test_create_missing_required_400() -> None:
    body = contract_body("DJ-INCOMPLETE")
    del body["witness"]
    resp = client().post(LIST_URL, body, format="json")
    assert resp.status_code == 400
    assert resp.json() == {
        "code": "BAD_REQUEST",
        "message": (
            "contractCode / clientUnit / projectName / constructionUnit / "
            "witnessUnit / witness are required"
        ),
    }


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I03")
def test_create_201_app_side_identity_from_claim() -> None:
    from entities.models import Contracts as Contract

    code = f"DJ-{uuid.uuid4().hex[:8].upper()}"
    payload = contract_body(code)
    payload["tenantId"] = "TENANT-EVIL"  # ADR-0019：body 传入值必须被忽略
    payload["status"] = "archived"
    resp = client().post(LIST_URL, payload, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert set(body) == CONTRACT_FIELDS
    # id/时间戳 app 侧生成（列全 text）
    assert body["id"] == str(uuid.UUID(body["id"]))  # uuid4 形态
    assert body["createdAt"] and body["updatedAt"]
    assert body["tenantId"] == TENANT
    assert body["status"] == "archived"
    row = Contract.objects.get(id=body["id"])
    assert row.tenant_id == TENANT  # stamp 自 token claim
    assert row.contract_code == code


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I03")
def test_create_default_status_active() -> None:
    body = create_via_api()
    assert body["status"] == "active"


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I03")
def test_create_duplicate_code_400() -> None:
    code = f"DJ-{uuid.uuid4().hex[:8].upper()}"
    assert client().post(LIST_URL, contract_body(code), format="json").status_code == 201
    resp = client().post(LIST_URL, contract_body(code), format="json")
    assert resp.status_code == 400  # PG 23505（idx_contracts_tenant_code）
    assert resp.json()["code"] == "BAD_REQUEST"
    assert resp.json()["message"] == "contractCode already exists for tenant"


# ---------- I02 合同详情 ----------
# （tree SSOT：I02=详情；本段 ID 以 docs/functions/function-tree.md 为准）


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I02")
def test_detail_200_seed_row() -> None:
    resp = client().get(f"{LIST_URL}/CONTRACT-001")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == CONTRACT_FIELDS
    assert body["id"] == "CONTRACT-001"
    assert body["contractCode"] == "HT-2026-001"
    assert body["tenantId"] == TENANT


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I02")
def test_detail_404_unknown_id() -> None:
    resp = client().get(f"{LIST_URL}/{DEAD_ID}")
    assert resp.status_code == 404
    assert resp.json() == {"code": "NOT_FOUND", "message": "Contract not found"}


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I02")
def test_detail_other_tenant_404() -> None:
    resp = client(tenant="TENANT-OTHER").get(f"{LIST_URL}/CONTRACT-001")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------- I04 更新合同 ----------


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I04")
def test_put_partial_merge_200() -> None:
    created = create_via_api()
    new_name = f"renamed-{uuid.uuid4().hex[:8]}"
    resp = client().put(f"{LIST_URL}/{created['id']}", {"projectName": new_name}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["projectName"] == new_name
    assert body["contractCode"] == created["contractCode"]  # 局部合并，其余不动
    assert body["id"] == created["id"]
    assert body["tenantId"] == TENANT


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I04")
def test_put_404_unknown_id() -> None:
    resp = client().put(f"{LIST_URL}/{DEAD_ID}", {"projectName": "x"}, format="json")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------- I05 删除合同 ----------


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I05")
def test_delete_204_then_repeat_404() -> None:
    created = create_via_api()
    resp = client().delete(f"{LIST_URL}/{created['id']}")
    assert resp.status_code == 204
    resp2 = client().delete(f"{LIST_URL}/{created['id']}")
    assert resp2.status_code == 404
    assert resp2.json()["code"] == "NOT_FOUND"


@pytest.mark.django_db
@pytest.mark.fn("M02.F01.I05")
def test_delete_404_unknown_id() -> None:
    resp = client().delete(f"{LIST_URL}/{DEAD_ID}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
