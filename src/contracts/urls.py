"""合同路由——契约面 /api/contracts（lab 无 /api/v1 前缀，CT PATH_LIST 同款）。"""

from __future__ import annotations

from django.urls import path

from contracts import views

urlpatterns = [
    path("contracts", views.ContractListCreateView.as_view()),
    path("contracts/<str:contract_id>", views.ContractDetailView.as_view()),
]
