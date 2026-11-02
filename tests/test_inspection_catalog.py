"""T4 基础数据码表 red-first：brands/models/specs/grades 4 实体同构 CRUD（16 端点）。

语义镜像 rails app/services/catalog/catalog_service.rb（Final review C-1 裁定收敛，
fastapi merge 语义为家族在册分叉不随）：
- tenant 收口：list 按 tenant 等值（claim tenant_id 优先，缺省 directory 默认租户）；
  update/delete 按 tenant+code 定位，他人租户行 miss → 404（隔离）
- create = 裸 create（rails create! 同款）：撞全局 code 唯一约束 → IntegrityError
  → 全局 handler 400 "constraint violation"（无 merge，无跨租户劫持），sortOrder 默认 0
- update = PATCH（None 跳过）+ updatedAt 刷新；无空载荷 400 特判无（跳过即 no-op）
- delete 命中 204 / miss 404；list 回显域分页：items 全量、page??1、pageSize??len、
  total=len，ORDER BY sort_order,code；keyword lower contains code/name
- DTO 出口 NON_NULL：None 键缺席

与字典域同款（ledger Task 3 Ruling）：lab_test 共库禁 TRUNCATE——自备行（唯一前缀
+ 唯一 keyword 过滤），django_db 事务回滚不污染。
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"cat4{uuid.uuid4().hex[:8]}"


def bearer(claims: dict | None = None) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims or {"sub": "alice"}).encode()).decode()
    return f"Bearer x.{payload}.y"


def client(claims: dict | None = None) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer(claims))
    return c


def uniq(prefix: str) -> str:
    return f"{prefix}-{TOKEN}"


# 各家族：路径 + 共享树锚前缀（M04.F06 型号 / F07 规格 / F08 等级 / F09 牌号）
FAMILIES = [
    ("models", "M04.F06"),
    ("specs", "M04.F07"),
    ("grades", "M04.F08"),
    ("brands", "M04.F09"),
]


# ---------------------------------------------------------------------------
# 4 家族 roundtrip（list → create → update → delete，各锚 I01-I04）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("name,prefix", FAMILIES)
@pytest.mark.fn("M04.F06.I01")
@pytest.mark.fn("M04.F06.I02")
@pytest.mark.fn("M04.F06.I03")
@pytest.mark.fn("M04.F06.I04")
@pytest.mark.fn("M04.F07.I01")
@pytest.mark.fn("M04.F07.I02")
@pytest.mark.fn("M04.F07.I03")
@pytest.mark.fn("M04.F07.I04")
@pytest.mark.fn("M04.F08.I01")
@pytest.mark.fn("M04.F08.I02")
@pytest.mark.fn("M04.F08.I03")
@pytest.mark.fn("M04.F08.I04")
@pytest.mark.fn("M04.F09.I01")
@pytest.mark.fn("M04.F09.I02")
@pytest.mark.fn("M04.F09.I03")
@pytest.mark.fn("M04.F09.I04")
def test_family_roundtrip(name: str, prefix: str) -> None:
    c = client()
    code_a, code_b = uniq(f"{prefix}A"), uniq(f"{prefix}B")
    # create（I02）：默认 sortOrder 显式传、remarks 可缺
    r = c.post(
        f"/api/catalog/{name}",
        {"code": code_a, "name": f"{TOKEN} 甲", "sortOrder": 2, "remark": "r1"},
        format="json",
    )
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["code"] == code_a
    assert body["name"] == f"{TOKEN} 甲"
    assert body["remark"] == "r1"
    assert body["tenantId"] == "TENANT-001"  # 无 claim → directory 默认租户
    assert "inspectionObjectCode" not in body  # NON_NULL：None 键缺席
    assert (
        c.post(
            f"/api/catalog/{name}",
            {"code": code_b, "name": f"{TOKEN} 乙", "sortOrder": 1},
            format="json",
        ).status_code
        == 200
    )
    # list（I01）：keyword 过滤 + 排序 sort_order,code + Page 回显
    r = c.get(f"/api/catalog/{name}", {"keyword": TOKEN})
    assert r.status_code == 200
    page = r.json()
    assert [i["code"] for i in page["items"]] == [code_b, code_a]
    assert page["total"] == 2
    assert page["page"] == 1
    assert page["pageSize"] == 2
    # objectCode 过滤
    r = c.get(f"/api/catalog/{name}", {"keyword": TOKEN, "inspectionObjectCode": "NOPE"})
    assert r.json()["total"] == 0
    # update（I03）：PATCH 局部合并
    time.sleep(0.01)
    r = c.put(f"/api/catalog/{name}/{code_a}", {"name": f"{TOKEN} 甲改"}, format="json")
    assert r.status_code == 200
    assert r.json()["name"] == f"{TOKEN} 甲改"
    assert r.json()["remark"] == "r1"  # 未传字段保留
    assert r.json()["updatedAt"] != body["createdAt"]
    assert (
        c.put(f"/api/catalog/{name}/nope{TOKEN}", {"name": "x"}, format="json").status_code == 404
    )
    # delete（I04）：204 → 404
    assert c.delete(f"/api/catalog/{name}/{code_a}").status_code == 204
    assert c.delete(f"/api/catalog/{name}/{code_a}").status_code == 404
    r = c.get(f"/api/catalog/{name}", {"keyword": TOKEN})
    assert [i["code"] for i in r.json()["items"]] == [code_b]


# ---------------------------------------------------------------------------
# 横切语义（models 家族锚 F06）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M04.F06.I02")
def test_create_defaults_and_missing_name_400() -> None:
    c = client()
    code = uniq("MD")
    r = c.post("/api/catalog/models", {"code": code, "name": f"{TOKEN} 默认"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["sortOrder"] == 0  # 默认 0
    assert body["createdAt"] == body["updatedAt"]
    r = c.post("/api/catalog/models", {"code": uniq("MDX")}, format="json")
    assert r.status_code == 400  # name 缺 → 400


@pytest.mark.django_db
@pytest.mark.fn("M04.F06.I02")
def test_same_code_post_conflict_400_no_tenant_hijack() -> None:
    """Final review C-1 修复红测试：rails/springboot 参照收敛——裸 create 撞全局 code
    唯一约束 → 400 constraint violation（无 merge，且无跨租户劫持——原 merge 路径
    会把他人租户行 tenant_id 改写劫持）。撞码 POST 包嵌套 atomic + set_rollback：
    IntegrityError 会毒化 pytest-django 外层事务，需 savepoint 回滚收口。"""
    from django.db import transaction

    c = client()
    code = uniq("MD")
    r = c.post("/api/catalog/models", {"code": code, "name": f"{TOKEN} 一"}, format="json")
    assert r.status_code == 200
    # 同租户撞 code → 400（rails RecordNotUnique → 400 constraint violation 镜像）
    with transaction.atomic():
        r = c.post("/api/catalog/models", {"code": code, "name": f"{TOKEN} 二"}, format="json")
        assert r.status_code == 400, r.content
        body = r.json()
        assert body["code"] == "BAD_REQUEST"
        assert "constraint violation" in body["message"]
        transaction.set_rollback(True)
    # 跨租户撞 code → 同样 400（原 merge 路径会 200 并劫持改写他人租户行）
    with transaction.atomic():
        other = client({"sub": "bob", "tenant_id": "TENANT-002"})
        r = other.post("/api/catalog/models", {"code": code, "name": "hijack"}, format="json")
        assert r.status_code == 400, r.content
        transaction.set_rollback(True)
    # 原行原封不动（归属/字段不变）
    r = c.get("/api/catalog/models", {"keyword": TOKEN})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["name"] == f"{TOKEN} 一"


@pytest.mark.django_db
@pytest.mark.fn("M04.F06.I03")
def test_update_partial_merge_skips_missing_fields() -> None:
    c = client()
    code = uniq("MD")
    c.post(
        "/api/catalog/models",
        {"code": code, "name": f"{TOKEN} 原", "remark": "keep"},
        format="json",
    )
    r = c.put(f"/api/catalog/models/{code}", {"sortOrder": 9}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == f"{TOKEN} 原"  # 未传不动
    assert body["sortOrder"] == 9
    assert body["remark"] == "keep"


@pytest.mark.django_db
@pytest.mark.fn("M04.F06.I01")
def test_tenant_isolation_scoped_list_update_delete() -> None:
    """tenant 收口：他人租户行 list 不可见，PUT/DELETE miss → 404。"""
    c = client()
    code = uniq("MD")
    c.post("/api/catalog/models", {"code": code, "name": f"{TOKEN} 隔离"}, format="json")
    other = client({"sub": "bob", "tenant_id": "TENANT-002"})
    r = other.get("/api/catalog/models", {"keyword": TOKEN})
    assert r.json()["total"] == 0  # 他人租户不可见
    assert other.put(f"/api/catalog/models/{code}", {"name": "x"}, format="json").status_code == 404
    assert other.delete(f"/api/catalog/models/{code}").status_code == 404
    # 本租户仍可见可改
    assert c.get("/api/catalog/models", {"keyword": TOKEN}).json()["total"] == 1


@pytest.mark.django_db
@pytest.mark.fn("M04.F06.I01")
def test_anonymous_401() -> None:
    c = APIClient()  # 无 Authorization
    assert c.get("/api/catalog/models").status_code == 401
    assert (
        c.post("/api/catalog/models", {"code": "x", "name": "y"}, format="json").status_code == 401
    )
    assert c.put("/api/catalog/models/x", {}, format="json").status_code == 401
    assert c.delete("/api/catalog/models/x").status_code == 401
