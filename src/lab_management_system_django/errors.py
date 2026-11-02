"""错误信封——401 形状逐字节对齐 nextjs requireTenant（contracts 路由族同款）：

{code: "UNAUTHORIZED", message: "tenant_id claim is required (ADR-0019)"}
其余异常落回 DRF 默认 handler（本切片 400/404 由 view 显式 Response 出）。
"""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import exception_handler

from authn.errors import ApiError


def envelope_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return Response(
            {"code": "UNAUTHORIZED", "message": "tenant_id claim is required (ADR-0019)"},
            status=401,
        )
    if isinstance(exc, ApiError):
        # 家族错误契约（authn 域）：GlobalExceptionHandler 镜像 {code,message} 信封
        return Response({"code": exc.code, "message": exc.message}, status=exc.status_code)
    return exception_handler(exc, context)
