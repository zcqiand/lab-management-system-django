"""错误信封——401 形状逐字节对齐 nextjs requireTenant（contracts 路由族同款）：

{code: "UNAUTHORIZED", message: "tenant_id claim is required (ADR-0019)"}
IntegrityError（FK/唯一约束违规）全局收口 400——rails application_controller
rescue_from InvalidForeignKey/RecordNotUnique → 400 "constraint violation" 镜像
（springboot DataIntegrityViolationException 同语义；Final review I-1/C-1 收敛，
此前 TR/CM/junction/receipts 的坏引用写路径落 DRF 默认 handler → 500 仓内自不一致）。
其余异常落回 DRF 默认 handler（本切片 400/404 由 view 显式 Response 出）。
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError
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
    if isinstance(exc, IntegrityError):
        return Response(
            {"code": "BAD_REQUEST", "message": f"constraint violation: {exc}"},
            status=400,
        )
    return exception_handler(exc, context)
