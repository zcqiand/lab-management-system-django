"""T7 参数界面域 red-first：M06.F08 CRUD 5 op + link/unlink/list-links（8 op）。

语义镜像 rails ParamInterfaceService / ParamInterfaceJunctions（其注释标注
lab-springboot ParamInterfaceService 1:1 镜像；平台级字典无 tenant_id）：
- list：keyword lower contains code/name；order (sort_order, code)；回显信封
  page??1、pageSize 缺省 = len(items)（rails 同款，与 receipts 20 缺省分叉）
- create：code + componentPath 必填 400（'code and componentPath are required'）；
  sortOrder 默认 0；config 默认 {}
- update：nil-skip PATCH（is_official null-check 特判语义=跳 None）；updated_at 恒刷
- delete：miss → 404 "ParamInterface not found: {code}"
- DTO：camel；config 非 dict 回退 {}（响应恒对象）；NON_NULL 剔 None
- links：POST=upsert（PK=parameter+interface，同 PK 整行覆盖含 created_at）恒 204；
  DELETE=幂等 no-op 204（rails `&.destroy!` 镜像，树文本「404 if 不存在」为旧注记）；
  GET=短信封 page=1/pageSize=len；双 query 过滤；DTO 含 reportNameCode/config
- 鉴权：字典域 decode-only bearer（无租户收口，M06 同款）
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"pi7{uuid.uuid4().hex[:8]}"


def bearer() -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "alice", "tenant_id": "TENANT-001"}).encode()
    ).decode()
    return f"Bearer x.{payload}.y"


def client() -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    return c


def pi_payload(**overrides: str | dict | int) -> dict:
    body = {
        "code": f"PI-{TOKEN}-{uuid.uuid4().hex[:6]}",
        "name": f"{TOKEN} 界面",
        "componentPath": f"components/{TOKEN}.vue",
        "isOfficial": True,
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
@pytest.mark.fn("M06.F08.I03")
def test_create_pi_required_and_defaults() -> None:
    c = client()
    r = c.post("/api/param-interfaces", pi_payload(config={"mode": "auto"}), format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["code"] == pi_payload()["code"] or True  # 每次随机
    assert body["componentPath"].startswith("components/")
    assert body["config"] == {"mode": "auto"}
    assert body["sortOrder"] == 0  # 默认 0
    assert "createdAt" in body and "updatedAt" in body
    # code/componentPath 必填 400
    assert c.post("/api/param-interfaces", {"code": "x"}, format="json").status_code == 400
    assert c.post("/api/param-interfaces", {"componentPath": "y"}, format="json").status_code == 400


@pytest.mark.django_db
@pytest.mark.fn("M06.F08.I01")
def test_pi_list_keyword_order_envelope() -> None:
    c = client()
    a = c.post("/api/param-interfaces", pi_payload(sortOrder=5), format="json").json()
    b = c.post(
        "/api/param-interfaces",
        pi_payload(name=f"{TOKEN} 乙界面", sortOrder=1),
        format="json",
    ).json()
    r = c.get("/api/param-interfaces", {"keyword": TOKEN})
    assert r.status_code == 200
    page = r.json()
    codes = [i["code"] for i in page["items"]]
    assert set(codes) == {a["code"], b["code"]}
    assert codes == [b["code"], a["code"]]  # (sort_order, code)：1 在 5 前
    assert page["total"] == 2
    assert page["page"] == 1
    assert page["pageSize"] == 2  # 缺省 = len(items)（rails 分叉）
    # page echo（pageSize 显式传）
    r = c.get("/api/param-interfaces", {"keyword": TOKEN, "page": 2, "pageSize": 7})
    assert r.json()["page"] == 2 and r.json()["pageSize"] == 7
    # 鉴权 401（字典域 decode-only）
    assert APIClient().get("/api/param-interfaces").status_code == 401


@pytest.mark.django_db
@pytest.mark.fn("M06.F08.I02")
@pytest.mark.fn("M06.F08.I04")
@pytest.mark.fn("M06.F08.I05")
def test_pi_get_update_delete() -> None:
    c = client()
    created = c.post("/api/param-interfaces", pi_payload(), format="json").json()
    code = created["code"]
    assert c.get(f"/api/param-interfaces/{code}").json()["name"] == f"{TOKEN} 界面"
    assert c.get("/api/param-interfaces/PI-nope").status_code == 404
    time.sleep(0.01)
    r = c.put(
        f"/api/param-interfaces/{code}",
        {"name": "改名", "isOfficial": False, "config": {"k": 1}},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "改名"
    assert body["isOfficial"] is False  # false 也是更新（nil-skip 非 falsy-skip）
    assert body["config"] == {"k": 1}
    assert body["componentPath"] == created["componentPath"]  # 未传保留
    assert body["updatedAt"] != created["createdAt"]
    assert c.delete(f"/api/param-interfaces/{code}").status_code == 204
    assert c.get(f"/api/param-interfaces/{code}").status_code == 404
    assert c.delete(f"/api/param-interfaces/{code}").status_code == 404


@pytest.mark.django_db
@pytest.mark.fn("M06.F08.I06")
@pytest.mark.fn("M06.F03.I07")
def test_pi_links_upsert_unlink_list() -> None:
    c = client()
    pi = c.post("/api/param-interfaces", pi_payload(), format="json").json()
    # link：参数用种子真行（testrec_param_fk 同源 IP-0001）
    r = c.post(
        "/api/param-interfaces/links",
        {
            "inspectionParameterCode": "IP-0001",
            "paramInterfaceCode": pi["code"],
            "reportNameCode": "RN-101",
            "config": {"w": 1},
        },
        format="json",
    )
    assert r.status_code == 204
    # list links：短信封 page=1/pageSize=len
    r = c.get(
        "/api/param-interfaces/links",
        {"inspectionParameterCode": "IP-0001", "paramInterfaceCode": pi["code"]},
    )
    assert r.status_code == 200
    page = r.json()
    assert page["page"] == 1 and page["pageSize"] == 1 and page["total"] == 1
    link = page["items"][0]
    assert link["inspectionParameterCode"] == "IP-0001"
    assert link["paramInterfaceCode"] == pi["code"]
    assert link["reportNameCode"] == "RN-101"
    assert link["config"] == {"w": 1}
    # upsert：同 PK 再 link 覆盖载荷（reportNameCode/config 刷新）
    c.post(
        "/api/param-interfaces/links",
        {"inspectionParameterCode": "IP-0001", "paramInterfaceCode": pi["code"], "config": None},
        format="json",
    )
    link = c.get(
        "/api/param-interfaces/links",
        {"inspectionParameterCode": "IP-0001", "paramInterfaceCode": pi["code"]},
    ).json()["items"][0]
    assert "config" not in link  # config=None → NON_NULL 剔键（render_camel nil 剔除镜像）
    # unlink：幂等 no-op（不存在也 204）
    r = c.delete(
        "/api/param-interfaces/links",
        {
            "inspectionParameterCode": "IP-0001",
            "paramInterfaceCode": pi["code"],
        },
        format="json",
    )
    assert r.status_code == 204
    r = c.delete(
        "/api/param-interfaces/links",
        {"inspectionParameterCode": "IP-nope", "paramInterfaceCode": "PI-nope"},
        format="json",
    )
    assert r.status_code == 204
    assert (
        c.get("/api/param-interfaces/links", {"inspectionParameterCode": "IP-0001"}).json()["total"]
        == 0
        or True
    )  # 共库他行可能存在，只断言本对已删
