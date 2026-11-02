"""authn 域 views —— 10 端点 DRF 薄壳（解析请求 → AuthService → Response）。

鉴权不走 DRF 全局链（AllowAny 公开挂载，身份校验在 service 内 require_bearer 显式
挂——fastapi「生成路由无全局鉴权兜底」同形）。错误由 errors.envelope_exception_handler
收口（ApiError → {code,message}）。
"""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError
from authn.service import AuthService

_service = AuthService()


def _body(request: Request) -> dict[str, Any]:
    data = getattr(request, "data", None)
    return data if isinstance(data, dict) else {}


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request: Request) -> Response:
    body = _body(request)
    return Response(
        _service.login(str(body.get("username") or ""), str(body.get("password") or ""))
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def native_login(request: Request) -> Response:
    body = _body(request)
    return Response(
        _service.native_login(str(body.get("username") or ""), str(body.get("password") or ""))
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def logout(_request: Request) -> Response:
    _service.logout()
    return Response(status=204)


@api_view(["GET"])
@permission_classes([AllowAny])
def me(request: Request) -> Response:
    return Response(_service.me(request))


@api_view(["POST"])
@permission_classes([AllowAny])
def switch_tenant(request: Request) -> Response:
    tenant_id = str(_body(request).get("tenantId") or "")
    return Response(_service.switch_tenant(request, tenant_id))


@api_view(["GET"])
@permission_classes([AllowAny])
def menus(request: Request) -> Response:
    return Response(_service.menus(request))


@api_view(["GET"])
@permission_classes([AllowAny])
def permissions(request: Request) -> Response:
    return Response(_service.permissions(request))


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh(request: Request) -> Response:
    token = _body(request).get("refreshToken")
    return Response(_service.refresh(str(token) if token is not None else ""))


@api_view(["GET"])
@permission_classes([AllowAny])
def sso_authorize(request: Request) -> Response:
    # 跳板形只消费 redirect_uri + state（response_type/client_id 被 service 忽略）
    return Response(
        _service.sso_authorize(
            request.query_params.get("redirect_uri"), request.query_params.get("state")
        )
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def sso_callback(request: Request) -> Response:
    body = _body(request)
    # 契约必填（snake_case 四键，openapi SsoCallbackRequest SSOT）；缺即 400 BAD_REQUEST
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    if not code or not redirect_uri:
        raise BadRequestError("code and redirect_uri are required")
    return Response(_service.sso_callback(str(code), str(redirect_uri)))
