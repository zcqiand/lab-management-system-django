"""T8 报告名称域 red-first：CRUD 5 op + 3 组 junction link/unlink/list（14 op）。

语义镜像 rails InspectionReportNameService / ReportNameJunctions（lab-springboot
镜像；平台级字典无 tenant_id）：
- list：keyword lower contains code/name；order (sort_order, code)；字典信封
  page??1、pageSize 缺省 = len(items)
- create：code/name 必填 400（'code and name are required'）；**create=JPA merge**
  （同 PK 覆盖整行含 createdAt——rails 2026-09-29 live 共库对拍实锤，T4 码表
  overwrite 裁定同族）；sortOrder 默认 0
- update：字段级判定（truthy 族跳 None；sortOrder 同）；updated_at 恒刷
- delete miss → 404 "ReportName not found: {code}"
- DTO：extFields 非 list 回退 []（响应恒数组）；NON_NULL 剔 None
- junction ×3：POST=upsert 恒 204（standard junction role 入 PK）；DELETE=幂等
  no-op 204（rails `&.destroy!`）；GET=短信封 page=1/pageSize=len + query 过滤
  （三组 GET 均为契约豁免辅助端点不挂 ID）
- 鉴权：字典域 decode-only bearer 无租户收口
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

TOKEN = f"rn8{uuid.uuid4().hex[:8]}"


def bearer() -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "alice", "tenant_id": "TENANT-001"}).encode()
    ).decode()
    return f"Bearer x.{payload}.y"


def client() -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    return c


def rn_payload(**overrides: str | list | int) -> dict:
    body = {
        "code": f"RN-{TOKEN}-{uuid.uuid4().hex[:6]}",
        "name": f"{TOKEN} 报告",
        "fullName": f"{TOKEN} 全名",
        "description": "测试报告名称",
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
@pytest.mark.fn("M06.F07.I03")
def test_create_rn_required_merge_defaults() -> None:
    c = client()
    r = c.post(
        "/api/report-names", rn_payload(extFields=[{"key": "壁厚", "type": "text"}]), format="json"
    )
    assert r.status_code == 200, r.content
    body = r.json()
    code = body["code"]
    assert body["name"] == f"{TOKEN} 报告"
    assert body["extFields"] == [{"key": "壁厚", "type": "text"}]
    assert body["sortOrder"] == 0  # 默认 0
    # create=merge：同 code 覆盖整行（name/extFields 刷新，createdAt 恒 now）
    first_created = body["createdAt"]
    time.sleep(0.01)
    r = c.post(
        "/api/report-names",
        rn_payload(code=code, name="覆写名", sortOrder=7),
        format="json",
    )
    assert r.status_code == 200
    body2 = r.json()
    assert body2["name"] == "覆写名"
    assert body2["sortOrder"] == 7
    assert body2["extFields"] == []  # merge 覆盖：未传 extFields → None → [] 回退
    assert body2["createdAt"] != first_created  # merge 恒刷 createdAt（rails save=merge 镜像）
    # code/name 必填 400
    assert c.post("/api/report-names", {"code": "x"}, format="json").status_code == 400
    assert c.post("/api/report-names", {"name": "y"}, format="json").status_code == 400


@pytest.mark.django_db
@pytest.mark.fn("M06.F07.I01")
def test_rn_list_keyword_order_envelope() -> None:
    c = client()
    a = c.post("/api/report-names", rn_payload(sortOrder=5), format="json").json()
    b = c.post(
        "/api/report-names",
        rn_payload(name=f"{TOKEN} 乙报告", sortOrder=1),
        format="json",
    ).json()
    r = c.get("/api/report-names", {"keyword": TOKEN})
    assert r.status_code == 200
    page = r.json()
    codes = [i["code"] for i in page["items"]]
    assert set(codes) == {a["code"], b["code"]}
    assert codes == [b["code"], a["code"]]  # (sort_order, code)
    assert page["total"] == 2
    assert page["page"] == 1
    assert page["pageSize"] == 2  # 缺省 = len(items)
    assert c.get("/api/report-names", {"keyword": "zzz-no-match"}).json()["total"] == 0
    assert APIClient().get("/api/report-names").status_code == 401


@pytest.mark.django_db
@pytest.mark.fn("M06.F07.I02")
@pytest.mark.fn("M06.F07.I04")
@pytest.mark.fn("M06.F07.I05")
def test_rn_get_update_delete() -> None:
    c = client()
    created = c.post("/api/report-names", rn_payload(), format="json").json()
    code = created["code"]
    assert c.get(f"/api/report-names/{code}").json()["fullName"] == f"{TOKEN} 全名"
    assert c.get("/api/report-names/RN-nope").status_code == 404
    time.sleep(0.01)
    r = c.put(
        f"/api/report-names/{code}",
        {"name": "改名", "sortOrder": 3},
        format="json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "改名" and body["sortOrder"] == 3
    assert body["fullName"] == f"{TOKEN} 全名"  # 未传保留
    assert body["updatedAt"] != created["createdAt"]
    assert c.delete(f"/api/report-names/{code}").status_code == 204
    assert c.get(f"/api/report-names/{code}").status_code == 404
    assert c.delete(f"/api/report-names/{code}").status_code == 404


@pytest.mark.django_db
@pytest.mark.fn("M06.F07.I06")
@pytest.mark.fn("M06.F04.I05")
@pytest.mark.fn("M06.F07.I07")
@pytest.mark.fn("M06.F04.I07")
@pytest.mark.fn("M06.F07.I08")
@pytest.mark.fn("M06.F04.I06")
def test_rn_junctions_link_unlink_list() -> None:
    c = client()
    rn = c.post("/api/report-names", rn_payload(), format="json").json()
    code = rn["code"]
    # object↔report-name：link → list → re-link 覆盖 remark → unlink 幂等
    assert (
        c.post(
            "/api/report-names/links/object",
            {"inspectionObjectCode": "OBJ-PG-T", "reportNameCode": code, "remark": "r1"},
            format="json",
        ).status_code
        == 204
    )
    page = c.get(
        "/api/report-names/links/object",
        {"inspectionObjectCode": "OBJ-PG-T", "reportNameCode": code},
    ).json()
    assert page["page"] == 1 and page["pageSize"] == 1
    assert page["items"][0]["remark"] == "r1"
    c.post(
        "/api/report-names/links/object",
        {"inspectionObjectCode": "OBJ-PG-T", "reportNameCode": code},
        format="json",
    )
    page = c.get(
        "/api/report-names/links/object",
        {"inspectionObjectCode": "OBJ-PG-T", "reportNameCode": code},
    ).json()
    assert "remark" not in page["items"][0]  # merge 覆盖 None → NON_NULL 剔键
    assert (
        c.delete(
            "/api/report-names/links/object",
            {"inspectionObjectCode": "OBJ-PG-T", "reportNameCode": code},
            format="json",
        ).status_code
        == 204
    )
    # 不存在也 204（幂等 no-op）
    assert (
        c.delete(
            "/api/report-names/links/object",
            {"inspectionObjectCode": "OBJ-nope", "reportNameCode": code},
            format="json",
        ).status_code
        == 204
    )
    # report-name↔standard(role)：role 入 PK（同 standard 不同 role 两条并存）
    assert (
        c.post(
            "/api/report-names/links/standard",
            {"reportNameCode": code, "inspectionStandardCode": "GB 1499.1-2024", "role": "TESTING"},
            format="json",
        ).status_code
        == 204
    )
    assert (
        c.post(
            "/api/report-names/links/standard",
            {
                "reportNameCode": code,
                "inspectionStandardCode": "GB 1499.1-2024",
                "role": "JUDGMENT",
            },
            format="json",
        ).status_code
        == 204
    )
    page = c.get(
        "/api/report-names/links/standard",
        {"reportNameCode": code, "role": "TESTING"},
    ).json()
    assert page["total"] == 1 and page["items"][0]["role"] == "TESTING"
    page = c.get("/api/report-names/links/standard", {"reportNameCode": code}).json()
    assert page["total"] == 2  # role 过滤缺省全量
    assert (
        c.delete(
            "/api/report-names/links/standard",
            {"reportNameCode": code, "inspectionStandardCode": "GB 1499.1-2024", "role": "TESTING"},
            format="json",
        ).status_code
        == 204
    )
    # report-name↔parameter
    assert (
        c.post(
            "/api/report-names/links/parameter",
            {"reportNameCode": code, "inspectionParameterCode": "IP-0001", "remark": "p"},
            format="json",
        ).status_code
        == 204
    )
    page = c.get(
        "/api/report-names/links/parameter",
        {"reportNameCode": code, "inspectionParameterCode": "IP-0001"},
    ).json()
    assert page["total"] == 1
    assert (
        c.delete(
            "/api/report-names/links/parameter",
            {"reportNameCode": code, "inspectionParameterCode": "IP-0001"},
            format="json",
        ).status_code
        == 204
    )
