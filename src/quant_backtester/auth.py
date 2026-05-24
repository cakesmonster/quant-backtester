"""API Key 认证中间件。

所有 /api/* 请求（除 /api/health 外）需携带 Authorization: Bearer <PUBLIC_KEY>。
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from quant_backtester.config import PUBLIC_KEY


# 不需要认证的 API 路径前缀
PUBLIC_PATHS = {"/api/health"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 非 API 路径跳过（静态页面等）
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # 公开路径跳过
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # /api/auth/verify 不需要认证（用于验证 key 是否有效）
        if request.method == "POST" and request.url.path == "/api/auth/verify":
            return await call_next(request)

        # 验证 Authorization header
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing Authorization header. Use: Bearer <key>"},
            )
        token = auth[len("Bearer "):]
        if token != PUBLIC_KEY:
            return JSONResponse(status_code=403, content={"error": "Invalid API key"})

        return await call_next(request)
