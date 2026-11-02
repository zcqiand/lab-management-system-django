"""T9 计算方法域 red-first：复合双键 CRUD 5 op（M06.F05.I01-I05）。

语义镜像 rails CalculationMethodService（lab-springboot 镜像；平台级字典
无 tenant_id，复合主键 object × parameter）：
- list：双过滤（inspectionObjectCode/inspectionParameterCode）+ order
  (sort_order, object, parameter)；**裸数组**（无分页信封，rails 分叉）
- create：双键任一缺失 400（'inspectionObjectCode and inspectionParameterCode
  are required'）；**create=JPA merge**（同双键覆盖整行含 createdAt）；
  缺省 algorithmType=manual / specimenCount=1 / sortOrder=0
- update：UPDATE_FIELDS truthy/strict 双判定（镜像 springboot mapper：
  truthy=值真值才写，strict=非 None 即写——specimenCount/sortOrder 可写 0）
- delete miss→404；DTO NON_NULL 递归剔 None 键
- FK：双键列带 DB FK，testingStandardCode/reportNameCode 亦 FK —— 测试自备
  父行（T3 同款真 API 造数 + 唯一 token）
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"cm9{uuid.uuid4().hex[:8]}"


def bearer() -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "alice", "tenant_id": "TENANT-001"}).encode()
    ).decode()
    return f"Bearer x.{payload}.y"


def client() -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    return c


def make_parents() -> tuple[str, str, str, str]:
    """自备 object/parameter/standard/report-name 父行（FK 列）。"""
    c = client()
    obj, param, std, rn = f"OBJ-{TOKEN}", f"IP-{TOKEN}", f"GB-{TOKEN}", f"RN-{TOKEN}"
    spc = f"SP-{TOKEN}"
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": spc, "officialNo": "OF-T9", "name": f"{TOKEN} 专项"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/objects",
            {
                "code": obj,
                "inspectionSpecialtyCode": spc,
                "sourceProjectNo": "PJ-T9",
                "sourceProjectName": f"{TOKEN} 工程项目",
                "name": f"{TOKEN} 项目",
            },
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/parameters",
            {"code": param, "name": f"{TOKEN} 参数", "rawName": "raw", "canonicalName": "canon"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/standards", {"code": std, "name": f"{TOKEN} 标准"}, format="json"
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/report-names", {"code": rn, "name": f"{TOKEN} 报告"}, format="json"
        ).status_code
        == 200
    )
    return obj, param, std, rn


def cm_payload(obj: str, param: str, std: str, rn: str, **overrides: object) -> dict:
    body = {
        "inspectionObjectCode": obj,
        "inspectionParameterCode": param,
        "testingStandardCode": std,
        "reportNameCode": rn,
        "formula": "R = F/A",
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
@pytest.mark.fn("M06.F05.I03")
def test_cm_create_required_defaults_merge() -> None:
    obj, param, std, rn = make_parents()
    c = client()
    r = c.post("/api/calculation-methods", cm_payload(obj, param, std, rn), format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["inspectionObjectCode"] == obj
    assert body["algorithmType"] == "manual"  # 缺省
    assert body["specimenCount"] == 1
    assert body["sortOrder"] == 0
    assert body["testingStandardCode"] == std
    first_created = body["createdAt"]
    # merge：同双键覆盖整行（algorithmType 刷新，未传 formula 抹掉）
    time.sleep(0.01)
    r = c.post(
        "/api/calculation-methods",
        cm_payload(obj, param, std, rn, algorithmType="formula", conditions="28d", formula=None),
        format="json",
    )
    assert r.status_code == 200
    body2 = r.json()
    assert body2["algorithmType"] == "formula"
    assert body2["conditions"] == "28d"
    assert "formula" not in body2  # merge 覆盖 None → 键缺席
    assert body2["createdAt"] != first_created
    # 双键任一缺失 400
    assert c.post("/api/calculation-methods", {}, format="json").status_code == 400
    assert (
        c.post("/api/calculation-methods", {"inspectionObjectCode": obj}, format="json").status_code
        == 400
    )


@pytest.mark.django_db
@pytest.mark.fn("M06.F05.I01")
def test_cm_list_dual_filter_bare_array() -> None:
    obj, param, std, rn = make_parents()
    param_y = f"IP-{TOKEN}-Y"
    obj_b = f"OBJ-{TOKEN}-B"
    spc = f"SP-{TOKEN}"  # make_parents 造的同 token 专项
    c = client()
    assert (
        c.post(
            "/api/inspection/parameters",
            {"code": param_y, "name": "乙", "rawName": "raw", "canonicalName": "canon"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/objects",
            {
                "code": obj_b,
                "inspectionSpecialtyCode": spc,
                "sourceProjectNo": "PJ-T9B",
                "sourceProjectName": f"{TOKEN} 乙工程项目",
                "name": "乙项目",
            },
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/calculation-methods", cm_payload(obj, param, std, rn, sortOrder=5), format="json"
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/calculation-methods",
            cm_payload(obj, param_y, std, rn, sortOrder=1),
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/calculation-methods", cm_payload(obj_b, param, std, rn), format="json"
        ).status_code
        == 200
    )
    r = c.get("/api/calculation-methods", {"inspectionObjectCode": obj})
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)  # 裸数组，无分页信封
    assert [i["inspectionParameterCode"] for i in items] == [param_y, param]  # sort_order
    r = c.get(
        "/api/calculation-methods",
        {"inspectionObjectCode": obj, "inspectionParameterCode": param},
    )
    assert [i["inspectionParameterCode"] for i in r.json()] == [param]
    assert APIClient().get("/api/calculation-methods").status_code == 401


@pytest.mark.django_db
@pytest.mark.fn("M06.F05.I02")
@pytest.mark.fn("M06.F05.I04")
@pytest.mark.fn("M06.F05.I05")
def test_cm_get_update_truthy_strict_delete() -> None:
    obj, param, std, rn = make_parents()
    c = client()
    created = c.post(
        "/api/calculation-methods", cm_payload(obj, param, std, rn), format="json"
    ).json()
    path = f"/api/calculation-methods/{obj}/{param}"
    assert c.get(path).json()["formula"] == "R = F/A"
    assert c.get(f"{path}-nope").status_code == 404
    time.sleep(0.01)
    # strict（非 None 即写）：specimenCount/sortOrder 可写 0；
    # truthy（真值才写）：algorithmType "" 跳过不变
    r = c.put(
        path,
        {"specimenCount": 0, "sortOrder": 3, "algorithmType": "", "roundingRule": "四舍五入"},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["specimenCount"] == 0
    assert body["sortOrder"] == 3
    assert body["algorithmType"] == "manual"  # truthy 空串跳过
    assert body["roundingRule"] == "四舍五入"
    assert body["updatedAt"] != created["createdAt"]
    assert c.delete(path).status_code == 204
    assert c.get(path).status_code == 404
    assert c.delete(path).status_code == 404
