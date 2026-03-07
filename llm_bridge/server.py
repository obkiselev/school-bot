"""Bearer-protected local bridge that proxies OpenAI-compatible calls to LM Studio."""
import hmac
import logging
import os
from typing import Optional

from aiohttp import ClientSession, ClientTimeout, web

logger = logging.getLogger("llm_bridge")


def _parse_bearer_token(auth_header: str | None) -> Optional[str]:
    if not auth_header:
        return None
    parts = auth_header.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0], parts[1].strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _is_authorized(auth_header: str | None, expected_token: str) -> bool:
    presented = _parse_bearer_token(auth_header)
    if not presented:
        return False
    return hmac.compare_digest(presented, expected_token)


def _strip_trailing_slash(url: str) -> str:
    return url.rstrip("/")


def _build_upstream_url(upstream_base: str, request_path_qs: str) -> str:
    return _strip_trailing_slash(upstream_base) + request_path_qs


def _collect_forward_headers(request: web.Request) -> dict[str, str]:
    allowed = {
        "accept",
        "content-type",
        "user-agent",
    }
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in allowed:
            headers[key] = value
    return headers


@web.middleware
async def _auth_middleware(request: web.Request, handler):
    if request.path == "/health":
        return await handler(request)

    token = request.app["bearer_token"]
    if not _is_authorized(request.headers.get("Authorization"), token):
        return web.json_response({"error": "unauthorized"}, status=401)

    return await handler(request)


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _proxy_v1(request: web.Request) -> web.Response:
    upstream_base: str = request.app["upstream_base"]
    timeout_seconds: int = request.app["timeout_seconds"]

    target_url = _build_upstream_url(upstream_base, request.rel_url.path_qs)
    body = await request.read()
    headers = _collect_forward_headers(request)

    logger.info("Proxying %s %s", request.method, request.rel_url.path_qs)

    timeout = ClientTimeout(total=timeout_seconds)

    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body if body else None,
            ) as upstream_response:
                response_body = await upstream_response.read()
                passthrough_headers = {}
                content_type = upstream_response.headers.get("Content-Type")
                if content_type:
                    passthrough_headers["Content-Type"] = content_type
                return web.Response(
                    status=upstream_response.status,
                    body=response_body,
                    headers=passthrough_headers,
                )
    except Exception as e:
        logger.exception("Proxy request failed for %s: %s", request.rel_url.path_qs, e)
        return web.json_response({"error": "upstream_unavailable"}, status=502)


def create_app() -> web.Application:
    bearer_token = os.getenv("LLM_BRIDGE_TOKEN", "").strip()
    if not bearer_token:
        raise RuntimeError("LLM_BRIDGE_TOKEN is required")

    upstream_base = os.getenv("LLM_UPSTREAM_BASE_URL", "http://127.0.0.1:1234").strip()
    timeout_seconds = int(os.getenv("LLM_BRIDGE_TIMEOUT", "45").strip())

    app = web.Application(middlewares=[_auth_middleware])
    app["bearer_token"] = bearer_token
    app["upstream_base"] = _strip_trailing_slash(upstream_base)
    app["timeout_seconds"] = timeout_seconds

    app.router.add_get("/health", _health)
    app.router.add_route("*", "/v1/{tail:.*}", _proxy_v1)
    return app


def main() -> None:
    logging.basicConfig(level=os.getenv("LLM_BRIDGE_LOG_LEVEL", "INFO"))
    app = create_app()
    host = os.getenv("LLM_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("LLM_BRIDGE_PORT", "8787"))
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()

