"""URL 路由——lab 契约面无 /api/v1 前缀（saas 仓是 /api/v1/**，刻意分叉不随）。"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path

from infra import views as infra_views

urlpatterns: list[URLPattern | URLResolver] = [
    # /health 家族探活（rails 同款：根路径匿名，contract-test healthcheck 目标；
    # 不进 manifest 的 infra 面，route parity allowlist 放行）
    path("health", infra_views.health),
    path("api/", include("contracts.urls")),
    path("api/", include("authn.urls")),
    path("api/", include("inspection.urls")),
    path("api/", include("receipts.urls")),
    path("api/", include("samples.urls")),
    path("api/", include("summary.urls")),
]
