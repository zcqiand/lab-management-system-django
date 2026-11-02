"""T11 基础设施面（T2 缓期收口）：GET /health 家族探活 + 家族 CORS 中间件。

不进功能树不动树（go /health 同款裁定——infra 端点不挂 fn-ID）：
- GET /health：匿名 200 {"status":"ok","stack":"django","family":"lab"}（rails
  HealthController 镜像；contract-test start-family.sh healthcheck 目标）
- CORS 中间件镜像 rails config/initializers/cors.rb（rack-cors）：origin 白名单
  读 LAB_CORS_ALLOWED_ORIGINS（fail-fast 无兜底）、headers :any（回显请求
  Access-Control-Request-Headers）、methods GET/POST/PUT/PATCH/DELETE/OPTIONS/HEAD、
  expose Authorization；白名单外 origin 不带任何 Allow 头
"""

from __future__ import annotations

from rest_framework.test import APIClient


def test_health_anonymous_ok() -> None:
    r = APIClient().get("/health")
    assert r.status_code == 200, r.content
    assert r.json() == {"status": "ok", "stack": "django", "family": "lab"}


def test_cors_preflight_allowed_origin() -> None:
    r = APIClient().options(
        "/api/contracts",
        HTTP_ORIGIN="http://localhost:5201",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
    )
    assert r.status_code == 200, r.content
    assert r["Access-Control-Allow-Origin"] == "http://localhost:5201"
    assert "POST" in r["Access-Control-Allow-Methods"]
    assert "DELETE" in r["Access-Control-Allow-Methods"]
    # headers :any —— 回显请求声明头（rack-cors 语义）
    assert r["Access-Control-Allow-Headers"] == "authorization,content-type"


def test_cors_simple_response_exposes_authorization() -> None:
    # 匿名 401 也带 CORS 头（跨域 SSO 登录失败也要让前端读得到响应）
    r = APIClient().get("/api/auth/me", HTTP_ORIGIN="http://localhost:5202")
    assert r.status_code == 401
    assert r["Access-Control-Allow-Origin"] == "http://localhost:5202"
    assert r["Access-Control-Expose-Headers"] == "Authorization"


def test_cors_disallowed_origin_no_headers() -> None:
    client = APIClient()
    r = client.get("/api/auth/me", HTTP_ORIGIN="http://evil.example")
    assert r.status_code == 401
    assert not r.has_header("Access-Control-Allow-Origin")
    pre = client.options(
        "/api/contracts",
        HTTP_ORIGIN="http://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert not pre.has_header("Access-Control-Allow-Origin")
