from django.urls import path

from samples import views

urlpatterns = [
    path("samples", views.samples),
    path("samples/<str:sample_id>", views.sample_detail),
    path("samples/<str:sample_id>/ext", views.sample_ext),
    path("test-records", views.test_records),
    path("test-records/<str:record_id>", views.test_record_detail),
    path("test-records/<str:record_id>/verdict", views.test_record_verdict),
]
