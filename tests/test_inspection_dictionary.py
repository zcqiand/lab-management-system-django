"""T3 检测字典面 red-first：专项/项目/参数/标准 CRUD + 4 junction 家族（28 端点）。

语义镜像 fastapi impl/inspection_dictionary_impl.py（其注释标注参照
lab-springboot InspectionDictionaryService / InspectionJunctionService）：
- 实体列表 Page 包裹不过滤：items=全量、page??1、pageSize??len、total=len；
  排序 sort_order,code；keyword lower(code/name) contains
- 实体 POST=200（非 201，springboot save→DTO 镜像）同 code 再 POST=全量覆盖；
  PUT=PATCH 局部合并；DELETE 204、重复删 404
- junction save()=upsert 覆盖全部载荷字段（含 None——JPA merge 语义）、
  unlink 幂等 204；junction list 固定 page=1、pageSize=size
- DTO 出口 NON_NULL 镜像：None 键缺席（re-link 空 remark 抹掉 remark 后键不在）

与 fastapi 测试的布局差异（ledger Task 3 Ruling）：lab_test 是 shared 全量种子共库
（specialties 10/parameters 587 行…），禁 TRUNCATE——测试自备行：唯一前缀代码走
真 API 造数 + 唯一 keyword 过滤断言，django_db 事务回滚不污染共库。
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from rest_framework.test import APIClient

# 唯一前缀 + 随机后缀：共库种子行（SP01…/OBJ-SP01-P1…）不可能撞
TOKEN = f"djt3{uuid.uuid4().hex[:8]}"


def bearer() -> str:
    """decode-only 假 token（字典面只要求可解析 payload，不要求 tenant_id）。"""
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "alice"}).encode()).decode()
    return f"Bearer x.{payload}.y"


def client() -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=bearer())
    return c


def uniq(prefix: str) -> str:
    return f"{prefix}-{TOKEN}"


# ---------------------------------------------------------------------------
# M06.F01.I01 检测专项列表
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F01.I01")
def test_specialty_list_wrapper_order_keyword_and_page_echo() -> None:
    code_a, code_b = uniq("SPA"), uniq("SPB")
    c = client()
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": code_a, "officialNo": "OF-A", "name": f"{TOKEN} 专项甲", "sortOrder": 1},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": code_b, "officialNo": "OF-B", "name": f"{TOKEN} 专项乙", "sortOrder": 2},
            format="json",
        ).status_code
        == 200
    )
    # 全量过滤出本测试两行，排序 sort_order,code
    resp = c.get("/api/inspection/specialties", {"keyword": TOKEN})
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert set(body) == {"items", "page", "pageSize", "total"}
    assert [i["code"] for i in body["items"]] == [code_a, code_b]
    assert body["page"] == 1
    assert body["pageSize"] == 2  # 缺省 = len(items)
    assert body["total"] == 2
    row = body["items"][0]
    assert row["officialNo"] == "OF-A"  # camelCase 出口
    assert row["createdAt"]  # 时间戳非空
    # page/pageSize 仅回显不过滤
    resp2 = c.get("/api/inspection/specialties", {"keyword": TOKEN, "page": "5", "pageSize": "1"})
    body2 = resp2.json()
    assert len(body2["items"]) == 2
    assert body2["page"] == 5
    assert body2["pageSize"] == 1
    assert body2["total"] == 2
    # keyword 大小写不敏感：小写片段命中大写 code（uniq 前缀 DJT3 小写匹配）
    lower_probe = c.get("/api/inspection/specialties", {"keyword": TOKEN.lower()})
    assert {i["code"] for i in lower_probe.json()["items"]} == {code_a, code_b}


@pytest.mark.django_db
@pytest.mark.fn("M06.F01.I02")
def test_specialty_create_defaults_and_missing_required_400() -> None:
    c = client()
    # 契约必填 officialNo 缺失 → 400 BAD_REQUEST
    resp = c.post(
        "/api/inspection/specialties",
        {"code": uniq("SPX"), "name": "缺官方编号"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["code"] == "BAD_REQUEST"
    # 最小载荷 → 默认值镜像（isOfficial/enabled=true、sortOrder=0）
    code = uniq("SP99")
    resp = c.post(
        "/api/inspection/specialties",
        {"code": code, "officialNo": "OF-99", "name": f"{TOKEN} 新专项"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert set(body) == {
        "code",
        "officialNo",
        "name",
        "isOfficial",
        "enabled",
        "sortOrder",
        "createdAt",
        "updatedAt",
    }
    assert body["code"] == code
    assert body["isOfficial"] is True
    assert body["enabled"] is True
    assert body["sortOrder"] == 0
    assert body["createdAt"]  # app 侧 UTC ISO 字符串


@pytest.mark.django_db
@pytest.mark.fn("M06.F01.I03")
def test_specialty_update_partial_and_missing_404() -> None:
    code = uniq("SPU")
    c = client()
    created = c.post(
        "/api/inspection/specialties",
        {"code": code, "officialNo": "OF-U", "name": f"{TOKEN} 待改"},
        format="json",
    ).json()
    time.sleep(0.01)  # 同微秒碰撞防护：updatedAt 断言需要 create/update 时间可分辨
    resp = c.put(f"/api/inspection/specialties/{code}", {"name": f"{TOKEN} 已改"}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["name"] == f"{TOKEN} 已改"
    assert body["officialNo"] == "OF-U"  # 部分更新：未提及字段不动
    assert body["isOfficial"] is True
    assert body["updatedAt"] != created["updatedAt"]
    resp = c.put("/api/inspection/specialties/NO-SUCH", {"name": "x"}, format="json")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.django_db
@pytest.mark.fn("M06.F01.I04")
def test_specialty_delete_204_then_404() -> None:
    code = uniq("SPD")
    c = client()
    # 无引用专项（不被任何 junction/下游引用——FK 500 路径不测，fastapi 同口径）
    resp = c.post(
        "/api/inspection/specialties",
        {"code": code, "officialNo": "OF-D", "name": f"{TOKEN} 待删"},
        format="json",
    )
    assert resp.status_code == 200
    assert c.delete(f"/api/inspection/specialties/{code}").status_code == 204
    resp = c.delete(f"/api/inspection/specialties/{code}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# M06.F02.I01 检测项目
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F02.I01")
def test_object_list_filters_and_page_echo() -> None:
    sp = uniq("SPF")
    obj_a, obj_b = uniq("OBJA"), uniq("OBJB")
    c = client()
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": sp, "officialNo": "OF-F", "name": f"{TOKEN} 宿主专项"},
            format="json",
        ).status_code
        == 200
    )
    for code, name, order in ((obj_a, f"{TOKEN} 锚杆proj", 1), (obj_b, f"{TOKEN} 钢筋proj", 2)):
        assert (
            c.post(
                "/api/inspection/objects",
                {
                    "code": code,
                    "inspectionSpecialtyCode": sp,
                    "sourceProjectNo": f"P-{TOKEN}",
                    "sourceProjectName": f"工程-{TOKEN}",
                    "name": name,
                    "sortOrder": order,
                },
                format="json",
            ).status_code
            == 200
        )
    # 专项过滤
    resp = c.get("/api/inspection/objects", {"inspectionSpecialtyCode": sp})
    assert [i["code"] for i in resp.json()["items"]] == [obj_a, obj_b]
    # keyword 命中 name
    resp = c.get("/api/inspection/objects", {"keyword": "锚杆proj"})
    assert [i["code"] for i in resp.json()["items"]] == [obj_a]
    # page/pageSize 仅回显不过滤
    body = c.get(
        "/api/inspection/objects", {"inspectionSpecialtyCode": sp, "page": "5", "pageSize": "1"}
    ).json()
    assert len(body["items"]) == 2
    assert body["page"] == 5
    assert body["pageSize"] == 1
    assert body["total"] == 2


@pytest.mark.django_db
@pytest.mark.fn("M06.F02.I02")
@pytest.mark.fn("M06.F02.I03")
@pytest.mark.fn("M06.F02.I04")
def test_object_create_defaults_and_update_delete() -> None:
    sp = uniq("SPO")
    code = uniq("OBJ99")
    c = client()
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": sp, "officialNo": "OF-O", "name": f"{TOKEN} 宿主"},
            format="json",
        ).status_code
        == 200
    )
    resp = c.post(
        "/api/inspection/objects",
        {
            "code": code,
            "inspectionSpecialtyCode": sp,
            "sourceProjectNo": f"P-{TOKEN}",
            "sourceProjectName": f"工程-{TOKEN}",
            "name": f"{TOKEN} 新项目",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert set(body) == {
        "code",
        "inspectionSpecialtyCode",
        "sourceProjectNo",
        "sourceProjectName",
        "name",
        "isOptionalForQualification",
        "isOfficial",
        "enabled",
        "sortOrder",
        "createdAt",
        "updatedAt",
    }
    assert body["isOptionalForQualification"] is False  # 默认 false
    assert body["isOfficial"] is True
    assert body["enabled"] is True
    assert body["sortOrder"] == 0
    resp = c.put(f"/api/inspection/objects/{code}", {"name": f"{TOKEN} 项目改"}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == f"{TOKEN} 项目改"
    assert body["inspectionSpecialtyCode"] == sp  # 局部合并不动其余
    assert c.delete(f"/api/inspection/objects/{code}").status_code == 204
    assert c.delete(f"/api/inspection/objects/{code}").status_code == 404


# ---------------------------------------------------------------------------
# M06.F02.I05/I06/I09 专项↔项目 junction
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F02.I05")
@pytest.mark.fn("M06.F02.I06")
@pytest.mark.fn("M06.F02.I09")
def test_specialty_object_link_upsert_overwrites_payload_unlink_idempotent() -> None:
    sp, obj = uniq("SPL"), uniq("OBJL")
    c = client()
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": sp, "officialNo": "OF-L", "name": f"{TOKEN} 关联专项"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/objects",
            {
                "code": obj,
                "inspectionSpecialtyCode": sp,
                "sourceProjectNo": f"P-{TOKEN}",
                "sourceProjectName": f"工程-{TOKEN}",
                "name": f"{TOKEN} 关联项目",
            },
            format="json",
        ).status_code
        == 200
    )
    url = "/api/inspection/links/specialty-object"
    resp = c.post(
        url,
        {"inspectionSpecialtyCode": sp, "inspectionObjectCode": obj, "remark": "新增关联"},
        format="json",
    )
    assert resp.status_code == 204, resp.content
    body = c.get(url, {"inspectionSpecialtyCode": sp}).json()
    assert body["total"] == 1
    assert body["page"] == 1  # junction list 固定 page=1、pageSize=size
    assert body["pageSize"] == 1
    assert body["items"][0]["remark"] == "新增关联"
    # 同键再 link：save()=upsert，载荷字段全部覆盖（None 也覆盖——JPA merge 语义）
    resp = c.post(url, {"inspectionSpecialtyCode": sp, "inspectionObjectCode": obj}, format="json")
    assert resp.status_code == 204
    body = c.get(url, {"inspectionSpecialtyCode": sp}).json()
    assert body["total"] == 1
    assert "remark" not in body["items"][0]  # NON_NULL 镜像
    # unlink 幂等 204
    assert (
        c.delete(
            url, {"inspectionSpecialtyCode": sp, "inspectionObjectCode": obj}, format="json"
        ).status_code
        == 204
    )
    assert (
        c.delete(
            url, {"inspectionSpecialtyCode": sp, "inspectionObjectCode": obj}, format="json"
        ).status_code
        == 204
    )
    assert c.get(url, {"inspectionSpecialtyCode": sp}).json()["total"] == 0


# ---------------------------------------------------------------------------
# M06.F02.I07/I08/I10 项目↔参数 junction
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F02.I07")
@pytest.mark.fn("M06.F02.I08")
@pytest.mark.fn("M06.F02.I10")
def test_object_parameter_link_requires_level_filters_and_unlink() -> None:
    obj, par = uniq("OBJP"), uniq("PARP")
    c = client()
    sp = uniq("SPP")
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": sp, "officialNo": "OF-P", "name": f"{TOKEN} 宿主P"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/objects",
            {
                "code": obj,
                "inspectionSpecialtyCode": sp,
                "sourceProjectNo": f"P-{TOKEN}",
                "sourceProjectName": f"工程-{TOKEN}",
                "name": f"{TOKEN} 项目P",
            },
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/parameters",
            {
                "code": par,
                "name": f"{TOKEN} 参数P",
                "rawName": f"{TOKEN} 原始名",
                "canonicalName": f"{TOKEN} 规范名",
            },
            format="json",
        ).status_code
        == 200
    )
    url = "/api/inspection/links/object-parameter"
    # 契约必填 qualificationLevel（生成契约必填，缺省路径不可达，显式传值——fastapi 澄清同款）
    resp = c.post(url, {"inspectionObjectCode": obj, "inspectionParameterCode": par}, format="json")
    assert resp.status_code == 400, resp.content
    assert resp.json()["code"] == "BAD_REQUEST"
    resp = c.post(
        url,
        {
            "inspectionObjectCode": obj,
            "inspectionParameterCode": par,
            "qualificationLevel": "RESTRICTED",
            "sourcePage": 3,
            "remark": "限值",
        },
        format="json",
    )
    assert resp.status_code == 204, resp.content
    # 单维过滤回读
    body = c.get(url, {"inspectionObjectCode": obj}).json()
    assert body["total"] == 1
    assert body["items"][0]["qualificationLevel"] == "RESTRICTED"
    body = c.get(url, {"inspectionParameterCode": par}).json()
    assert body["total"] == 1
    # 双维不命中
    assert (
        c.get(url, {"inspectionObjectCode": uniq("NONE"), "inspectionParameterCode": par}).json()[
            "total"
        ]
        == 0
    )
    # unlink 请求体不含 qualificationLevel（纯键 DTO）
    assert (
        c.delete(
            url, {"inspectionObjectCode": obj, "inspectionParameterCode": par}, format="json"
        ).status_code
        == 204
    )
    assert c.get(url, {"inspectionObjectCode": obj}).json()["total"] == 0


# ---------------------------------------------------------------------------
# M06.F03.I01/I02 检测参数
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F03.I01")
@pytest.mark.fn("M06.F03.I02")
def test_parameter_list_source_type_filter_and_defaults() -> None:
    par_official, par_custom = uniq("PARO"), uniq("PARC")
    c = client()
    # 最小载荷 → 默认值镜像（aliases=[]、sourceType=official、sortOrder=0）
    resp = c.post(
        "/api/inspection/parameters",
        {
            "code": par_official,
            "name": f"{TOKEN} 碳化深度",
            "rawName": f"{TOKEN} 碳化深度",
            "canonicalName": f"{TOKEN} 碳化深度",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert set(body) == {
        "code",
        "name",
        "rawName",
        "canonicalName",
        "aliases",
        "sourceType",
        "sortOrder",
        "createdAt",
        "updatedAt",
    }
    assert body["sourceType"] == "official"
    assert body["aliases"] == []
    assert body["sortOrder"] == 0
    # aliases jsonb roundtrip（部分更新：其余字段不动）
    resp = c.put(
        f"/api/inspection/parameters/{par_official}",
        {"aliases": [f"{TOKEN} 碳化值"], "unit": "mm"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["aliases"] == [f"{TOKEN} 碳化值"]
    assert body["unit"] == "mm"
    assert body["name"] == f"{TOKEN} 碳化深度"
    # sourceType=custom 显式建 + 过滤（keyword 双保险唯一样本）
    assert (
        c.post(
            "/api/inspection/parameters",
            {
                "code": par_custom,
                "name": f"{TOKEN} 自定义参数",
                "rawName": f"{TOKEN} 自定义",
                "canonicalName": f"{TOKEN} 自定义",
                "sourceType": "custom",
            },
            format="json",
        ).status_code
        == 200
    )
    resp = c.get("/api/inspection/parameters", {"sourceType": "custom", "keyword": par_custom})
    assert [i["code"] for i in resp.json()["items"]] == [par_custom]
    # 删除 204 → 404
    assert c.delete(f"/api/inspection/parameters/{par_official}").status_code == 204
    resp = c.delete(f"/api/inspection/parameters/{par_official}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.django_db
@pytest.mark.fn("M06.F03.I02")
def test_parameter_create_missing_required_400() -> None:
    resp = client().post(
        "/api/inspection/parameters",
        {"code": uniq("PARX"), "name": "缺别名全称"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["code"] == "BAD_REQUEST"


# ---------------------------------------------------------------------------
# M06.F03.I05/I06/I08 标准↔参数 junction
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F03.I05")
@pytest.mark.fn("M06.F03.I06")
@pytest.mark.fn("M06.F03.I08")
def test_standard_parameter_link_flow() -> None:
    std, par = uniq("STDP"), uniq("PARS")
    c = client()
    assert (
        c.post(
            "/api/inspection/standards",
            {"code": std, "name": f"{TOKEN} 标准S"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/parameters",
            {
                "code": par,
                "name": f"{TOKEN} 参数S",
                "rawName": f"{TOKEN} 原始S",
                "canonicalName": f"{TOKEN} 规范S",
            },
            format="json",
        ).status_code
        == 200
    )
    url = "/api/inspection/links/standard-parameter"
    assert (
        c.post(
            url, {"inspectionStandardCode": std, "inspectionParameterCode": par}, format="json"
        ).status_code
        == 204
    )
    assert c.get(url, {"inspectionStandardCode": std}).json()["total"] == 1
    assert c.get(url, {"inspectionParameterCode": par}).json()["total"] == 1
    body = c.get(url, {"inspectionStandardCode": std}).json()["items"][0]
    assert set(body) == {"inspectionStandardCode", "inspectionParameterCode"}  # 纯键 DTO
    # unlink 幂等
    assert (
        c.delete(
            url, {"inspectionStandardCode": std, "inspectionParameterCode": par}, format="json"
        ).status_code
        == 204
    )
    assert (
        c.delete(
            url, {"inspectionStandardCode": std, "inspectionParameterCode": par}, format="json"
        ).status_code
        == 204
    )
    assert c.get(url, {"inspectionStandardCode": std}).json()["total"] == 0


# ---------------------------------------------------------------------------
# M06.F04.I01-I04 检测标准
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F04.I01")
@pytest.mark.fn("M06.F04.I02")
@pytest.mark.fn("M06.F04.I03")
@pytest.mark.fn("M06.F04.I04")
def test_standard_list_status_filter_and_crud() -> None:
    std_a, std_b, std_new = uniq("STDA"), uniq("STDB"), uniq("STD99")
    c = client()
    assert (
        c.post(
            "/api/inspection/standards",
            {"code": std_a, "name": f"{TOKEN} 规范甲", "status": "active"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/standards",
            {"code": std_b, "name": f"{TOKEN} 规范乙", "status": "superseded"},
            format="json",
        ).status_code
        == 200
    )
    assert [
        i["code"]
        for i in c.get("/api/inspection/standards", {"status": "active", "keyword": TOKEN}).json()[
            "items"
        ]
    ] == [std_a]
    assert [
        i["code"]
        for i in c.get(
            "/api/inspection/standards", {"status": "superseded", "keyword": TOKEN}
        ).json()["items"]
    ] == [std_b]
    assert {
        i["code"] for i in c.get("/api/inspection/standards", {"keyword": TOKEN}).json()["items"]
    } == {std_a, std_b}
    # 最小载荷 → status 默认 active
    resp = c.post(
        "/api/inspection/standards", {"code": std_new, "name": f"{TOKEN} 新标准"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert set(body) == {
        "code",
        "name",
        "status",
        "sortOrder",
        "createdAt",
        "updatedAt",
    }
    assert body["status"] == "active"
    assert body["sortOrder"] == 0
    resp = c.put(
        f"/api/inspection/standards/{std_new}",
        {"status": "superseded", "version": "2025"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "superseded"
    assert body["version"] == "2025"
    assert body["name"] == f"{TOKEN} 新标准"
    assert c.delete(f"/api/inspection/standards/{std_new}").status_code == 204
    assert c.delete(f"/api/inspection/standards/{std_new}").status_code == 404


# ---------------------------------------------------------------------------
# M06.F01.I05/I06/I07 项目↔标准 junction（role 是键部件）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F01.I05")
@pytest.mark.fn("M06.F01.I06")
@pytest.mark.fn("M06.F01.I07")
def test_object_standard_link_role_is_key_part() -> None:
    sp, obj, std = uniq("SPR"), uniq("OBJR"), uniq("STDR")
    c = client()
    assert (
        c.post(
            "/api/inspection/specialties",
            {"code": sp, "officialNo": "OF-R", "name": f"{TOKEN} 宿主R"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/objects",
            {
                "code": obj,
                "inspectionSpecialtyCode": sp,
                "sourceProjectNo": f"P-{TOKEN}",
                "sourceProjectName": f"工程-{TOKEN}",
                "name": f"{TOKEN} 项目R",
            },
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/inspection/standards", {"code": std, "name": f"{TOKEN} 标准R"}, format="json"
        ).status_code
        == 200
    )
    url = "/api/inspection/links/object-standard"
    # 同 (object, standard) 异 role = 不同键
    assert (
        c.post(
            url,
            {"inspectionObjectCode": obj, "inspectionStandardCode": std, "role": "TESTING"},
            format="json",
        ).status_code
        == 204
    )
    assert (
        c.post(
            url,
            {"inspectionObjectCode": obj, "inspectionStandardCode": std, "role": "JUDGMENT"},
            format="json",
        ).status_code
        == 204
    )
    body = c.get(url, {"inspectionObjectCode": obj}).json()
    assert body["total"] == 2
    assert [
        i["inspectionStandardCode"]
        for i in c.get(url, {"inspectionObjectCode": obj, "role": "TESTING"}).json()["items"]
    ] == [std]
    assert [
        i["inspectionStandardCode"]
        for i in c.get(url, {"inspectionObjectCode": obj, "role": "JUDGMENT"}).json()["items"]
    ] == [std]
    # unlink 带 role 键；未命中静默 no-op（幂等 204）
    assert (
        c.delete(
            url,
            {"inspectionObjectCode": obj, "inspectionStandardCode": std, "role": "TESTING"},
            format="json",
        ).status_code
        == 204
    )
    assert (
        c.delete(
            url,
            {"inspectionObjectCode": obj, "inspectionStandardCode": std, "role": "TESTING"},
            format="json",
        ).status_code
        == 204
    )
    assert c.get(url, {"inspectionObjectCode": obj, "role": "TESTING"}).json()["total"] == 0
    assert c.get(url, {"inspectionObjectCode": obj, "role": "JUDGMENT"}).json()["total"] == 1


# ---------------------------------------------------------------------------
# 统一镜像语义：字典面 28 端点全部 require_login（匿名 401 抽查五面各一）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.fn("M06.F01.I01")
def test_anonymous_401_across_five_surfaces() -> None:
    for path in (
        "/api/inspection/specialties",
        "/api/inspection/objects",
        "/api/inspection/parameters",
        "/api/inspection/standards",
        "/api/inspection/links/specialty-object",
    ):
        resp = APIClient().get(path)
        assert resp.status_code == 401, f"{path} → {resp.status_code}"
