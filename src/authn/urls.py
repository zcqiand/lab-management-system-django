"""authn 路由——契约面 /api/auth/**（lab 无 /api/v1 前缀）。"""

from __future__ import annotations

from django.urls import path

from authn import views

urlpatterns = [
    path("auth/login", views.login),
    path("auth/native-login", views.native_login),
    path("auth/logout", views.logout),
    path("auth/me", views.me),
    path("auth/menus", views.menus),
    path("auth/permissions", views.permissions),
    path("auth/refresh", views.refresh),
    path("auth/switch-tenant", views.switch_tenant),
    path("auth/sso/authorize", views.sso_authorize),
    path("auth/sso/callback", views.sso_callback),
]
