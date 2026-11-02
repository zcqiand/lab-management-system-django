"""接样单面路由（契约 SSOT = shared openapi；14 op = CRUD 5 + history 1 + task 1
+ 七段 act 7）。"""

from __future__ import annotations

from django.urls import path

from receipts import views

urlpatterns = [
    # M03.F01.I01/I03 CRUD 收口
    path("receipts", views.receipts),
    # M03.F01.I02/I04/I05 详情（GET/PUT/DELETE 同路径分发）
    path("receipts/<str:receipt_id>", views.receipt_detail),
    # M03.F01.I06 流程历史
    path("receipts/<str:receipt_id>/history", views.receipt_history),
    # M03.F02.I01 任务分配
    path("receipts/<str:receipt_id>/task", views.receipt_task),
    # 七段 act（M03.F01.I08 / F02.I05 / F03.I12 / F05.I07 / F06.I05 / F07.I05 / F08.I05）
    path("receipts/receiving/act", views.act_receiving),
    path("receipts/assigning/act", views.act_assigning),
    path("receipts/data-entry/act", views.act_data_entry),
    path("receipts/review/act", views.act_review),
    path("receipts/approve/act", views.act_approve),
    path("receipts/issuance/act", views.act_issuance),
    path("receipts/archived/act", views.act_archived),
]
