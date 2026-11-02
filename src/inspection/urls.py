"""检测字典面路由（契约 SSOT = shared openapi；28 op = 4 实体 CRUD + 4 junction
家族；同路径多方法由 views 路径级分发层收口，Django path 按 URL 路由不分方法）。"""

from __future__ import annotations

from django.urls import path

from inspection import (
    calculation_method_views,
    catalog_views,
    param_interface_views,
    report_name_views,
    technical_requirement_views,
    views,
)

urlpatterns = [
    # 基础数据码表 M04.F06-F09（4 实体同构 CRUD，16 op）
    path("catalog/brands", catalog_views.catalog_brands),
    path("catalog/brands/<str:code>", catalog_views.catalog_brand_detail),
    path("catalog/grades", catalog_views.catalog_grades),
    path("catalog/grades/<str:code>", catalog_views.catalog_grade_detail),
    path("catalog/models", catalog_views.catalog_models),
    path("catalog/models/<str:code>", catalog_views.catalog_model_detail),
    path("catalog/specs", catalog_views.catalog_specs),
    path("catalog/specs/<str:code>", catalog_views.catalog_spec_detail),
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
    # 参数界面 M06.F08（CRUD 5 + link/unlink/list-links）；静态 links 路径必须在
    # <str:code> 前声明（Django 顺序匹配，镜像 rails/springboot 字面路径优先语义）
    path("param-interfaces/links", param_interface_views.param_interface_links),
    path("param-interfaces", param_interface_views.param_interfaces),
    path("param-interfaces/<str:code>", param_interface_views.param_interface_detail),
    # 报告名称 M06.F07（CRUD 5 + 3 组 junction 9 op）；静态 links 路径在 <str:code> 前
    path("report-names/links/object", report_name_views.object_links),
    path("report-names/links/standard", report_name_views.standard_links),
    path("report-names/links/parameter", report_name_views.parameter_links),
    path("report-names", report_name_views.report_names),
    path("report-names/<str:code>", report_name_views.report_name_detail),
    # 计算方法 M06.F05（复合双键）+ 技术要求 M06.F06（复合三键）
    path("calculation-methods", calculation_method_views.calculation_methods),
    path(
        "calculation-methods/<str:inspection_object_code>/<str:inspection_parameter_code>",
        calculation_method_views.calculation_method_detail,
    ),
    path("technical-requirements", technical_requirement_views.technical_requirements),
    path(
        "technical-requirements/<str:inspection_object_code>"
        "/<str:inspection_parameter_code>/<str:judgment_standard_code>",
        technical_requirement_views.technical_requirement_detail,
    ),
]
