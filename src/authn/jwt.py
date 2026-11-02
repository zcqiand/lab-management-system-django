"""JWT 签发/校验 + Bearer 提取 —— lab-springboot LabJwtSigner 镜像（fastapi
impl/security.py 同源）。

- HS256，JWT_SIGNING_KEY ≥32 字节；claims iss/sub/tenant_id?/typ/iat/exp
  （lab JWT **无 aud/jti/nbf** —— 与 saas 仓 JwtIssuer 的差异点，verify_aud=False）
- refresh token typ=refresh，内嵌 saas_refresh_token claim（lab 无状态不持 saas 会话）
- PyJWT encode 默认 sort_keys → 与 springboot TreeMap 字典序 payload 一致
"""

from __future__ import annotations

import jwt
from django.http import HttpRequest

from authn.config import AuthConfig
from authn.errors import BadRequestError, InvalidCredentialsError


def _epoch() -> int:
    import datetime  # noqa: PLC0415 局部面窄

    return int(datetime.datetime.now(datetime.UTC).timestamp())


class JwtIssuer:
    def __init__(self, config: AuthConfig) -> None:
        if len(config.jwt_signing_key.encode()) < 32:
            raise RuntimeError("JWT_SIGNING_KEY must be >=32 bytes for HS256")
        self._key = config.jwt_signing_key
        self._issuer = config.jwt_issuer
        self._access_ttl = config.jwt_ttl_seconds
        self._refresh_ttl = config.jwt_refresh_ttl_seconds

    def issue(self, user_id: str, tenant_id: str | None) -> str:
        """签 access token；tenantId 可空（无选租户时不带 claim）。"""
        now = _epoch()
        payload: dict[str, object] = {
            "sub": user_id,
            "iat": now,
            "exp": now + self._access_ttl,
            "typ": "access",
            "iss": self._issuer,
        }
        if tenant_id:
            payload["tenant_id"] = tenant_id
        return str(jwt.encode(payload, self._key, algorithm="HS256"))

    def issue_refresh(self, user_id: str, saas_refresh_token: str) -> str:
        """签 refresh token，载荷内嵌 saas refresh token；空值 400。"""
        if not saas_refresh_token:
            raise BadRequestError("saasRefreshToken required for refresh token")
        now = _epoch()
        payload: dict[str, object] = {
            "sub": user_id,
            "saas_refresh_token": saas_refresh_token,
            "iat": now,
            "exp": now + self._refresh_ttl,
            "typ": "refresh",
            "iss": self._issuer,
        }
        return str(jwt.encode(payload, self._key, algorithm="HS256"))

    def verify(self, token: str) -> dict[str, object]:
        """验签 + iss + exp（PyJWT 默认含 exp 校验）；失败 401。"""
        if not token:
            raise InvalidCredentialsError("token is empty")
        try:
            claims: dict[str, object] = jwt.decode(
                token,
                key=self._key,
                algorithms=["HS256"],
                issuer=self._issuer,
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise InvalidCredentialsError(str(exc)) from exc
        return claims


def require_bearer(request: HttpRequest, issuer: JwtIssuer) -> dict[str, object]:
    """取当前 Bearer 身份：无/坏 → 401（authn views 自行挂，不走 DRF 全局鉴权）。"""
    header = request.headers.get("Authorization")
    if header is None or not header.startswith("Bearer "):
        raise InvalidCredentialsError("Bearer token required")
    return issuer.verify(header[len("Bearer ") :].strip())
