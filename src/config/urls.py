"""URL 路由——lab 契约面无 /api/v1 前缀（saas 仓是 /api/v1/**，刻意分叉不随）。"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("api/", include("contracts.urls")),
]
