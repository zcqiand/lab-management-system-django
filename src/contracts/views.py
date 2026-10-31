"""合同管理五端点（M02.F01 I01-I05）——语义对齐 nextjs oracle（跨栈一致）。

- list：token 租户过滤 + status eq + keyword icontains（contractCode/projectName）+
  1-based 分页切片（CT T11 live 实证，page=1/pageSize=20 默认），wrapper
  {items, page, pageSize, total}——分页内联在 list()，不子类化 BasePagination
  （其 paginate_queryset 签名方法级 TypeVar，具体化即 Liskov 红，saas 同坑）
- create：必填 6 项缺一 400 BAD_REQUEST（逐字对齐 nextjs message）；id/时间戳
  app 侧生成；tenant_id 只取 token claim（ADR-0019，body.tenantId 忽略）；
  撞 idx_contracts_tenant_code 唯一索引 PG 23505 -> 400
- detail/put/delete：租户收口，未知/跨租户一律 404 NOT_FOUND；PUT = Object.assign
  局部合并（白名单内），updatedAt 重写；DELETE 204、重复删 404
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from django.db import IntegrityError
from django.db.models import Q, QuerySet
from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from contracts.models import Contract
from contracts.serializers import ContractSerializer
from lab_management_system_django.auth import Principal

# 可经 POST/PUT 写的列（camelCase -> 模型属性；id/tenantId/createdAt 路由层控制）
CONTRACT_COLUMNS: dict[str, str] = {
    "contractCode": "contract_code",
    "clientUnit": "client_unit",
    "projectName": "project_name",
    "projectLocation": "project_location",
    "constructionUnit": "construction_unit",
    "inspectionSpecialtyCode": "inspection_specialty_code",
    "buildingUnit": "building_unit",
    "supervisorUnit": "supervisor_unit",
    "inspectionPerson": "inspection_person",
    "inspectionPhone": "inspection_phone",
    "witnessUnit": "witness_unit",
    "witness": "witness",
    "witnessPhone": "witness_phone",
    "contactPerson": "contact_person",
    "contactPhone": "contact_phone",
    "entrustedDate": "entrusted_date",
    "status": "status",
}
REQUIRED_FIELDS = (
    "contractCode",
    "clientUnit",
    "projectName",
    "constructionUnit",
    "witnessUnit",
    "witness",
)
REQUIRED_MESSAGE = (
    "contractCode / clientUnit / projectName / constructionUnit / "
    "witnessUnit / witness are required"
)


def _now_iso() -> str:
    """JS toISOString 同款形状（毫秒 + Z）。"""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_page_param(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


def _principal(request: Request) -> Principal:
    """Bearer 层（lab_management_system_django.auth）保证 authenticated 即 Principal；
    测试 force-credential 走真 Authorization 头，属性面一致。"""
    return cast(Principal, request.user)


def _body_str(body: dict[str, object], key: str) -> str:
    """nextjs String(body[key] ?? "") 同款：缺省/None 归空串，其余 str()。"""
    value = body.get(key)
    return "" if value is None else str(value)


def _apply_patch(contract: Contract, body: dict[str, object], *, touch_updated_at: bool) -> None:
    """Object.assign 局部合并：白名单内且 body 给出的字段才覆盖。"""
    for key, attr in CONTRACT_COLUMNS.items():
        if key in body and body[key] is not None:
            setattr(contract, attr, _body_str(body, key))
    if touch_updated_at:
        contract.updated_at = _now_iso()


class ContractListCreateView(generics.ListCreateAPIView[Contract]):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer

    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        tenant_id = _principal(request).tenant_id
        queryset = Contract.objects.filter(tenant_id=tenant_id)
        status = request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        keyword = request.query_params.get("keyword") or ""
        if keyword:
            queryset = queryset.filter(
                Q(contract_code__icontains=keyword) | Q(project_name__icontains=keyword)
            )
        page = max(1, _parse_page_param(request.query_params.get("page"), 1))
        page_size = _parse_page_param(request.query_params.get("pageSize"), 20)
        total = queryset.count()
        items = list(queryset[(page - 1) * page_size : page * page_size])
        data = [ContractSerializer(c).data for c in items]
        return Response({"items": data, "page": page, "pageSize": page_size, "total": total})

    def create(  # noqa: ARG002 (DRF 分发签名，args/kwargs 由 ruff variadic 豁免)
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        if any(not _body_str(body, field) for field in REQUIRED_FIELDS):
            return Response({"code": "BAD_REQUEST", "message": REQUIRED_MESSAGE}, status=400)
        now = _now_iso()
        contract = Contract(
            id=str(uuid.uuid4()),
            tenant_id=_principal(request).tenant_id,  # 只认 claim，body.tenantId 忽略
            status=_body_str(body, "status") or "active",
            created_at=now,
            updated_at=now,
        )
        _apply_patch(contract, body, touch_updated_at=False)
        try:
            contract.save()
        except IntegrityError:
            # idx_contracts_tenant_code 唯一索引（tenant_id, contract_code）-> PG 23505
            return Response(
                {"code": "BAD_REQUEST", "message": "contractCode already exists for tenant"},
                status=400,
            )
        return Response(ContractSerializer(contract).data, status=201)


class ContractDetailView(APIView):
    def get(self, request: Request, contract_id: str) -> Response:
        contract = self._scoped(request).filter(id=contract_id).first()
        if contract is None:
            return self._not_found()
        return Response(ContractSerializer(contract).data, status=200)

    def put(self, request: Request, contract_id: str) -> Response:
        contract = self._scoped(request).filter(id=contract_id).first()
        if contract is None:
            return self._not_found()
        body = request.data if isinstance(request.data, dict) else {}
        _apply_patch(contract, body, touch_updated_at=True)
        contract.save()
        return Response(ContractSerializer(contract).data, status=200)

    def delete(self, request: Request, contract_id: str) -> Response:
        deleted, _ = self._scoped(request).filter(id=contract_id).delete()
        if not deleted:
            return self._not_found()
        return Response(status=204)

    @staticmethod
    def _scoped(request: Request) -> QuerySet[Contract, Contract]:
        return Contract.objects.filter(tenant_id=_principal(request).tenant_id)

    @staticmethod
    def _not_found() -> Response:
        return Response({"code": "NOT_FOUND", "message": "Contract not found"}, status=404)
