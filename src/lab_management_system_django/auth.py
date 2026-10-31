"""Bearer 解析（decode-only）——lab 家族语义（nextjs oracle src/lib/auth/bearer.ts 同款）。

与 saas 家族刻意分叉：lab 各后端不校验 JWT 签名（saas token 不出 lab 后端；
lab 自家签发在 M01.F05 后置），这里只 base64url 解 payload 取 tenant_id claim。
缺失/无效 -> None -> DRF NotAuthenticated -> errors.envelope_exception_handler 401。
ADR-0019：写路径租户身份只认 claim，禁 body 传入、禁 demo 字面量兜底。
"""

from __future__ import annotations

import base64
import binascii
import json

from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request


class Principal:
    """最小请求主体——非 django User（family 库无 django 表）；属性面对齐 view 消费。"""

    is_authenticated = True

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id


class BearerAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[Principal, None] | None:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header[len("Bearer ") :]
        parts = token.split(".")
        if len(parts) != 3:
            return None
        try:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        except (ValueError, binascii.Error, UnicodeDecodeError):
            return None
        tenant_raw = payload.get("tenant_id") if isinstance(payload, dict) else None
        if not isinstance(tenant_raw, str) or not tenant_raw:
            return None
        return Principal(tenant_raw), None

    def authenticate_header(self, _request: Request) -> str:
        return "Bearer"
