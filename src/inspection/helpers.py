"""检测能力域共享 helper —— fastapi impl/inspection_support.py 同源镜像（其注释
标注参照 lab-springboot 五个 Inspection*Service 公共形状）：

- now_iso()          → springboot nowIso() UTC ISO_OFFSET（+00:00 后缀）镜像
- require_login()    → 逐端点显式挂（生成路由无全局鉴权兜底）；decode-only bearer
  （lab 家族语义，design-function-map「关键语义分叉」），字典实体平台级无租户列
  （V012），只要求可解析 payload——不复用 contracts 的 BearerAuthentication
  （其强制 tenant_id claim 是租户收口业务面语义）
- keyword_hit()      → lower(code/name) contains 镜像（None → 不过滤）
- upsert_junction()  → JPA save()=merge 镜像：同主键覆盖全部载荷字段（含 None）
- unlink_junction()  → 未命中静默 no-op（unlink 幂等）
- get_or_404()       → miss → 404 NOT_FOUND 镜像
- require_non_blank()→ requireNonBlank → 400 镜像
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any

from django.http import HttpRequest

from authn.errors import BadRequestError, InvalidCredentialsError, NotFoundError


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _decode_claims(request: HttpRequest) -> dict[str, Any]:
    """decode-only bearer 三段解析；缺/坏 → 401 INVALID_CREDENTIALS。"""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise InvalidCredentialsError("Bearer token required")
    parts = header[len("Bearer ") :].strip().split(".")
    if len(parts) != 3:
        raise InvalidCredentialsError("Bearer token required")
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidCredentialsError("Bearer token required") from None
    if not isinstance(payload, dict):
        raise InvalidCredentialsError("Bearer token required")
    return payload


def require_login(request: HttpRequest) -> None:
    """decode-only bearer：Bearer 三段可解析 payload 即过（不取 claims）。"""
    _decode_claims(request)


def require_login_claims(request: HttpRequest) -> dict[str, Any]:
    """decode-only bearer + 返回 payload（码表 tenant 收口取 tenant_id claim 用）。"""
    return _decode_claims(request)


def current_tenant_or_default(claims: dict[str, Any]) -> str:
    """springboot currentTenantIdOrDefault 镜像：claim tenant_id 非空用之，否则
    directory 默认租户（TENANT-001 业务码，非 env fallback——fastapi 2026-10-01
    CT live 修正同款）。"""
    claim = claims.get("tenant_id")
    if claim is not None and str(claim).strip():
        return str(claim)
    from authn.state import registry

    return registry().directory.default_tenant().tenant_id


def scoped_row_or_404(model: type[Any], code: str, tenant: str, label: str) -> Any:
    """findByTenantIdAndCode 镜像：他人租户行 miss → 404（隔离语义）。"""
    row = model.objects.filter(code=code).first()
    if row is None or row.tenant_id != tenant:
        raise NotFoundError(f"{label} not found: {code}")
    return row


def keyword_hit(keyword: str | None, code: str, name: str) -> bool:
    """lower(code) contains OR lower(name) contains；keyword None/空 → 不过滤。"""
    if keyword is None:
        return True
    needle = keyword.lower()
    return needle in code.lower() or needle in name.lower()


def require_non_blank(**fields: str | None) -> None:
    """键字段 blank 校验镜像（requireNonBlank → 400）。"""
    for name, value in fields.items():
        if value is None or not str(value).strip():
            raise BadRequestError(f"{name} is required")


def get_or_404(model: type[Any], code: str) -> Any:
    """主键取行；miss → 404 NOT_FOUND。"""
    try:
        return model.objects.get(code=code)
    except model.DoesNotExist:
        raise NotFoundError(f"resource not found: {code}") from None


def upsert_junction(
    model: type[Any], key_values: dict[str, Any], payload_values: dict[str, Any]
) -> None:
    """JPA save()=merge 镜像：命中主键 → 覆盖全部载荷字段（含 None，第二次 link
    空 remark 抹掉 remark）；未命中 → 新增行。"""
    now = now_iso()
    row = model.objects.filter(**key_values).first()
    if row is None:
        model.objects.create(**key_values, **payload_values, created_at=now, updated_at=now)
        return
    for name, value in payload_values.items():
        setattr(row, name, value)
    row.updated_at = now
    row.save(update_fields=[*payload_values, "updated_at"])


def unlink_junction(model: type[Any], key_values: dict[str, Any]) -> None:
    """DELETE 幂等镜像：按键删，未命中静默 no-op（204 由 view 收口）。"""
    model.objects.filter(**key_values).delete()
