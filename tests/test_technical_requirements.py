"""T9 技术要求域 red-first：复合三键 CRUD 5 op（M06.F06.I01-I05）。

语义镜像 rails TechnicalRequirementService / TechnicalRequirementFields
（lab-springboot 镜像；tenant-scoped，复合主键 object × parameter × standard）：
- list：4 过滤（object/parameter/standard/verificationStatus）+ tenant 收口；
  order (sort_order, object, parameter, standard)；**裸数组**（无分页信封）
- create：三键任一缺失 400（'inspectionObjectCode/inspectionParameterCode/
  judgmentStandardCode are required'）；**create=JPA merge**（同三键+同租户
  覆盖整行含 createdAt）；枚举缺省 valueType=numeric / comparison=≥ /
  judgmentMode=manual / verificationStatus=draft（`body[k] || default`）；
  NULLABLE 15 键直透；sortOrder 默认 0
- update：全字段跳 None；updated_at 恒刷；delete miss→404
- 隔离：他人租户行 miss → 404 境外不可见
- DTO：NON_NULL 递归剔 None 键
- FK：三键列全带 DB FK —— 测试自备父字典行（T3 同款真 API 造数 + 唯一 token）
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"tr9{uuid.uuid4().hex[:8]}"


def bearer(tenant: str = "TENANT-001") -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "alice", "tenant_id": tenant}).encode()
    ).decode()
    return f"Bearer x.{payload}.y"


def client(tenant: str = "TENANT-001") -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer(tenant))
    return c


def make_parents() -> tuple[str, str, str]:
    """自备 object/parameter/standard 父行（三键列全带 DB FK）。"""
    c = client()
    obj, param, std = f"OBJ-{TOKEN}", f"IP-{TOKEN}", f"GB-{TOKEN}"
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
    return obj, param, std


def tr_payload(obj: str, param: str, std: str, **overrides: object) -> dict:
    body = {
        "inspectionObjectCode": obj,
        "inspectionParameterCode": param,
        "judgmentStandardCode": std,
        "conditions": "标准养护 28d",
        "targetValue": "25.0",
        "unit": "MPa",
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
@pytest.mark.fn("M06.F06.I03")
def test_tr_create_required_defaults_merge() -> None:
    obj, param, std = make_parents()
    c = client()
    r = c.post("/api/technical-requirements", tr_payload(obj, param, std), format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["inspectionObjectCode"] == obj
    assert body["tenantId"] == "TENANT-001"
    assert body["valueType"] == "numeric"  # 枚举缺省
    assert body["comparison"] == "≥"
    assert body["judgmentMode"] == "manual"
    assert body["verificationStatus"] == "draft"
    assert body["sortOrder"] == 0
    assert body["targetValue"] == "25.0"
    assert "minValue" not in body  # NULLABLE 直透 None → NON_NULL 剔键
    first_created = body["createdAt"]
    # merge：同三键+同租户覆盖整行（enum/nullable 刷新，未传键抹掉）
    time.sleep(0.01)
    r = c.post(
        "/api/technical-requirements",
        tr_payload(
            obj,
            param,
            std,
            valueType="string",
            verificationStatus="reviewed",
            conditions=None,
            targetValue=None,
            unit=None,
        ),
        format="json",
    )
    assert r.status_code == 200
    body2 = r.json()
    assert body2["valueType"] == "string"
    assert body2["verificationStatus"] == "reviewed"
    assert "conditions" not in body2  # merge 覆盖 None → 键缺席
    assert body2["createdAt"] != first_created  # merge 恒刷 createdAt
    # 三键任一缺失 400
    assert c.post("/api/technical-requirements", {}, format="json").status_code == 400
    assert (
        c.post(
            "/api/technical-requirements",
            {"inspectionObjectCode": obj},
            format="json",
        ).status_code
        == 400
    )


@pytest.mark.django_db
@pytest.mark.fn("M06.F06.I01")
def test_tr_list_filters_order_bare_array() -> None:
    obj, param, std = make_parents()
    std_b, std_c = f"GB-{TOKEN}-B", f"GB-{TOKEN}-C"
    c = client()
    assert (
        c.post(
            "/api/inspection/standards", {"code": std_b, "name": "乙"}, format="json"
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/standards", {"code": std_c, "name": "丙"}, format="json"
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/technical-requirements",
            tr_payload(obj, param, std, sortOrder=5),
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/technical-requirements",
            tr_payload(obj, param, std_b, sortOrder=1),
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/technical-requirements",
            tr_payload(obj, param, std_c, verificationStatus="reviewed"),
            format="json",
        ).status_code
        == 200
    )
    r = c.get("/api/technical-requirements", {"inspectionObjectCode": obj})
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)  # 裸数组，无分页信封
    assert [i["judgmentStandardCode"] for i in items] == [std_c, std_b, std]  # sort_order, std
    r = c.get(
        "/api/technical-requirements",
        {"inspectionObjectCode": obj, "judgmentStandardCode": std_b},
    )
    assert [i["judgmentStandardCode"] for i in r.json()] == [std_b]
    r = c.get("/api/technical-requirements", {"inspectionParameterCode": param})
    assert len(r.json()) == 3
    r = c.get(
        "/api/technical-requirements",
        {"inspectionObjectCode": obj, "verificationStatus": "reviewed"},
    )
    assert [i["judgmentStandardCode"] for i in r.json()] == [std_c]
    assert APIClient().get("/api/technical-requirements").status_code == 401


@pytest.mark.django_db
@pytest.mark.fn("M06.F06.I02")
@pytest.mark.fn("M06.F06.I04")
@pytest.mark.fn("M06.F06.I05")
def test_tr_get_update_delete_tenant_isolation() -> None:
    obj, param, std = make_parents()
    c = client()
    created = c.post(
        "/api/technical-requirements", tr_payload(obj, param, std), format="json"
    ).json()
    path = f"/api/technical-requirements/{obj}/{param}/{std}"
    assert c.get(path).json()["targetValue"] == "25.0"
    assert c.get(f"{path}-nope").status_code == 404  # 不存在组合 → 404
    time.sleep(0.01)
    r = c.put(path, {"verificationStatus": "verified", "targetValue": "26.5"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["verificationStatus"] == "verified"
    assert body["targetValue"] == "26.5"
    assert body["conditions"] == "标准养护 28d"  # 未传保留
    assert body["updatedAt"] != created["createdAt"]
    # 他人租户行境外不可见（隔离 miss → 404）
    assert client("TENANT-002").get(path).status_code == 404
    assert c.delete(path).status_code == 204
    assert c.get(path).status_code == 404
    assert c.delete(path).status_code == 404
