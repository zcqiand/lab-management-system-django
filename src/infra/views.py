"""基础设施面视图 —— GET /health 家族探活（rails HealthController 镜像）。

不挂鉴权、不进功能树不动树（go /health 同款裁定）：contract-test
start-family.sh healthcheck 目标，只证明进程活着；DB 探活由 gate L4 真库链
负责（fail-not-skip）。响应形状与 rails 对齐：{"status":"ok","stack":<栈>,"family":"lab"}。
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "stack": "django", "family": "lab"})
