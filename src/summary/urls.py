"""M05 统计面路由（GET /api/summary + /api/summary/stats）+
_frontend-bind/snapshot 占位端点（契约面有 op，无实现 → 404）。"""

from __future__ import annotations

from django.urls import path

from summary import views

urlpatterns = [
    path("summary", views.summary),
    path("summary/stats", views.summary_stats),
    path("_frontend-bind/snapshot", views.frontend_bind_snapshot),
]
