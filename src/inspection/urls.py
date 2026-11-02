"""检测字典面路由（契约 SSOT = shared openapi；28 op = 4 实体 CRUD + 4 junction
家族；同路径多方法由 views 路径级分发层收口，Django path 按 URL 路由不分方法）。"""

from __future__ import annotations

from django.urls import path

from inspection import views

urlpatterns = [
    # 专项 M06.F01.I01-I04
    path("inspection/specialties", views.specialties),
    path("inspection/specialties/<str:code>", views.specialty_detail),
    # 项目 M06.F02.I01-I04
    path("inspection/objects", views.objects),
    path("inspection/objects/<str:code>", views.object_detail),
    # 参数 M06.F03.I01-I04
    path("inspection/parameters", views.parameters),
    path("inspection/parameters/<str:code>", views.parameter_detail),
    # 标准 M06.F04.I01-I04
    path("inspection/standards", views.standards),
    path("inspection/standards/<str:code>", views.standard_detail),
    # junction 家族（M06.F02.I05/I06/I09、M06.F02.I07/I08/I10、
    # M06.F01.I05/I06/I07、M06.F03.I05/I06/I08）
    path("inspection/links/specialty-object", views.specialty_object_links),
    path("inspection/links/object-parameter", views.object_parameter_links),
    path("inspection/links/object-standard", views.object_standard_links),
    path("inspection/links/standard-parameter", views.standard_parameter_links),
]
