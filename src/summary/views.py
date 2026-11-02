"""M05 报告汇总 + 仪表盘统计 views —— rails SummaryController 镜像（2 端点，
tenant 从 claim 取）。stats 走 wire 键直出（不走 camel 变换，见 service 注记）。"""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from authn.errors import NotFoundError
from inspection.helpers import current_tenant_or_default, require_login_claims
from summary.service import dashboard_stats, report_summary


def _query(request: Request, name: str) -> str | None:
    value = request.GET.get(name)
    return value if value else None


@api_view(["GET"])
@permission_classes([AllowAny])
def summary(request: Request) -> Response:
    tenant = current_tenant_or_default(require_login_claims(request))
    return Response(
        report_summary(
            tenant,
            _query(request, "categoryCode"),
            _query(request, "dateFrom"),
            _query(request, "dateTo"),
        )
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def summary_stats(request: Request) -> Response:
    tenant = current_tenant_or_default(require_login_claims(request))
    return Response(dashboard_stats(tenant))


@api_view(["GET"])
@permission_classes([AllowAny])
def frontend_bind_snapshot(request: Request) -> Response:
    """生成器 DTO 占位端点（rails/go 同款裁定）：DTO 存在但无后端实现——挂认证
    （springboot Security 链先于 404 handler，匿名 401），登录后 404 NOT_FOUND。"""
    require_login_claims(request)
    raise NotFoundError("resource not found")
