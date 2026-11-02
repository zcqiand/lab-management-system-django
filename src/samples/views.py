"""样品 + 检测记录域 12 端点 views —— rails SamplesController /
TestRecordsController 逐条镜像。

- list 回显信封（BusinessEnvelope 镜像）：page??1、pageSize??20 缺省，items 全量
- create 200（rails render_camel 镜像）；delete 204
- 鉴权：decode-only bearer（逐端点显式 require_login_claims）+ tenant_id claim
  缺省 directory 默认租户（码表面同款 helpers）
"""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError
from inspection.helpers import current_tenant_or_default, require_login_claims
from samples import service


def _body(request: Request) -> dict[str, Any]:
    data = getattr(request, "data", None)
    return data if isinstance(data, dict) else {}


def _query(request: Request, name: str) -> str | None:
    value = request.GET.get(name)
    return value if value else None


def _int_param(request: Request, name: str, default: int) -> int:
    raw = request.GET.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise BadRequestError("invalid integer value") from None


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def samples(request: Request) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    if request.method == "POST":
        return Response(service.create_sample(tenant, _body(request)), status=200)
    items = service.list_samples(tenant, _query(request, "receiptId"), _query(request, "keyword"))
    return Response(
        {
            "items": items,
            "page": _int_param(request, "page", 1),
            "pageSize": _int_param(request, "pageSize", 20),
            "total": len(items),
        }
    )


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([AllowAny])
def sample_detail(request: Request, sample_id: str) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    if request.method == "GET":
        return Response(service.get_sample(tenant, sample_id))
    if request.method == "PUT":
        return Response(service.update_sample(tenant, sample_id, _body(request)))
    service.delete_sample(tenant, sample_id)
    return Response(status=204)


@api_view(["PUT"])
@permission_classes([AllowAny])
def sample_ext(request: Request, sample_id: str) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    return Response(service.update_sample_ext(tenant, sample_id, _body(request)))


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def test_records(request: Request) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    if request.method == "POST":
        return Response(service.create_record(tenant, _body(request)), status=200)
    items = service.list_records(tenant, _query(request, "sampleId"))
    return Response(
        {
            "items": items,
            "page": _int_param(request, "page", 1),
            "pageSize": _int_param(request, "pageSize", 20),
            "total": len(items),
        }
    )


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([AllowAny])
def test_record_detail(request: Request, record_id: str) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    if request.method == "GET":
        return Response(service.get_record(tenant, record_id))
    if request.method == "PUT":
        return Response(service.update_record(tenant, record_id, _body(request)))
    service.delete_record(tenant, record_id)
    return Response(status=204)


@api_view(["PATCH"])
@permission_classes([AllowAny])
def test_record_verdict(request: Request, record_id: str) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    body = _body(request)
    return Response(service.set_verdict(tenant, record_id, body.get("verdict")))
