"""接样单域 14 端点 views —— rails ReceiptsController 逐条镜像（B3：CRUD + history +
任务分配 + 7 阶段全 act 模式）。

- 列表信封（BusinessEnvelope 镜像）：{items, page, pageSize, total}；page??1、
  pageSize??20 缺省（2026-09-16 T11 live 实证 1-based）；items 全量不切片
- 7 个 act 端点共享 body {ids[], action, operator, reason?}，stage 由路径定：
  assigning→task_assignment、approve→approval（rails 同款映射）
- create 返回 200（springboot save→DTO 镜像）；delete 204
- 鉴权：decode-only bearer（逐端点显式 require_login）+ tenant_id claim 缺省
  directory 默认租户（码表面同款 helpers）
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import BadRequestError
from inspection.helpers import current_tenant_or_default, require_login_claims
from receipts import flow, service


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
def receipts(request: Request) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    if request.method == "POST":
        return Response(service.create(tenant, _body(request)), status=200)
    items = service.list_receipts(
        tenant,
        _query(request, "contractId"),
        _query(request, "flowStatus"),
        _query(request, "keyword"),
        _query(request, "filter"),
    )
    # BusinessEnvelope 镜像：page=1/pageSize=20 缺省，仅 echo 不切片
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
def receipt_detail(request: Request, receipt_id: str) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    if request.method == "GET":
        return Response(service.get(tenant, receipt_id))
    if request.method == "PUT":
        return Response(service.update(tenant, receipt_id, _body(request)))
    service.delete(tenant, receipt_id)
    return Response(status=204)


@api_view(["GET"])
@permission_classes([AllowAny])
def receipt_history(request: Request, receipt_id: str) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    return Response(service.clean_dto(service.history(tenant, receipt_id)))


@api_view(["PUT"])
@permission_classes([AllowAny])
def receipt_task(request: Request, receipt_id: str) -> Response:
    claims = require_login_claims(request)
    tenant = current_tenant_or_default(claims)
    return Response(service.assign_task(tenant, receipt_id, _body(request)))


def _act_view(stage: str) -> Callable[..., Any]:
    """7 个 act 端点共享形状（stage 由路径定）。"""

    def view(request: Request) -> Response:
        claims = require_login_claims(request)
        tenant = current_tenant_or_default(claims)
        return Response(flow.act(stage, _body(request), service, tenant))

    view.__name__ = (
        f"act_{stage}"  # 装饰前设（catalog_views 同款，django-stubs AsView 无 __name__）
    )
    return api_view(["POST"])(permission_classes([AllowAny])(view))


act_receiving = _act_view("receiving")
act_assigning = _act_view("task_assignment")
act_data_entry = _act_view("data_entry")
act_review = _act_view("review")
act_approve = _act_view("approval")
act_issuance = _act_view("issuance")
act_archived = _act_view("archived")
