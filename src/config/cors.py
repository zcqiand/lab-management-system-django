"""家族 CORS 契约中间件 —— 镜像 rails config/initializers/cors.rb（rack-cors）。

origin 白名单读 LAB_CORS_ALLOWED_ORIGINS（逗号分隔），fail-fast 无默认兜底
（suite 硬规则 §1；rails ENV.fetch 同语义）；headers :any（回显请求
Access-Control-Request-Headers）、methods 镜像 rack-cors
%i[get post put patch delete options head]、expose Authorization。
自写 40 行中间件不引 django-cors-headers：pyproject 运行时依赖面保持最小
（go 仓 stdlib 自写同款裁定），T2 缓期本批收口（REQ-2026-035 T11）。
"""

from __future__ import annotations

import os
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

_ALLOWED_METHODS = "GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD"


def _allowed_origins() -> set[str]:
    raw = os.environ.get("LAB_CORS_ALLOWED_ORIGINS")
    if not raw:
        raise RuntimeError("env LAB_CORS_ALLOWED_ORIGINS required（禁默认值兜底，suite 硬规则 §1）")
    return {o.strip() for o in raw.split(",") if o.strip()}


class FamilyCorsMiddleware:
    """白名单 origin 的响应补家族 CORS 头；OPTIONS 预检短路（rack-cors resource '*'）。"""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.origins = _allowed_origins()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        origin = request.headers.get("Origin", "")
        allowed = origin in self.origins
        if request.method == "OPTIONS" and "Access-Control-Request-Method" in request.headers:
            response = HttpResponse(status=200)
            if allowed:
                response["Access-Control-Allow-Origin"] = origin
                response["Access-Control-Allow-Methods"] = _ALLOWED_METHODS
                response["Access-Control-Allow-Headers"] = request.headers.get(
                    "Access-Control-Request-Headers", "*"
                )
            return response
        response = self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Expose-Headers"] = "Authorization"
        return response
