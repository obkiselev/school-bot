"""Monkey-patch OctoDiary AsyncBaseAPI.request() для поддержки SOCKS5 прокси.

OctoDiary использует голый aiohttp.ClientSession() без прокси.
Этот патч проверяет атрибут `_socks_proxy` на экземпляре API
и создаёт ProxyConnector из aiohttp-socks если прокси задан.

Импортировать этот модуль в bot.py ДО любых вызовов OctoDiary.
"""
import logging
from typing import Optional

import aiohttp
from octodiary.apis.base import AsyncBaseAPI, Type

logger = logging.getLogger(__name__)

_original_request = AsyncBaseAPI.request


async def _request_with_proxy(
    self,
    method: str,
    base_url: str,
    path: str,
    custom_headers: Optional[dict] = None,
    model: Optional[type[Type]] = None,
    is_list: bool = False,
    return_json: bool = False,
    return_raw_text: bool = False,
    required_token: bool = True,
    return_raw_response: bool = False,
    **kwargs,
):
    proxy_url = getattr(self, "_socks_proxy", None)
    if not proxy_url:
        return await _original_request(
            self,
            method=method,
            base_url=base_url,
            path=path,
            custom_headers=custom_headers,
            model=model,
            is_list=is_list,
            return_json=return_json,
            return_raw_text=return_raw_text,
            required_token=required_token,
            return_raw_response=return_raw_response,
            **kwargs,
        )

    from aiohttp_socks import ProxyConnector

    connector = ProxyConnector.from_url(proxy_url)
    params = kwargs.pop("params", {})

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.request(
            method=method,
            url=self.init_params(str(base_url) + path, params),
            headers=self.headers(required_token, custom_headers),
            **kwargs,
        ) as response:
            await self._check_response(response)
            raw_text = await response.text()

            if not raw_text:
                return None

            return (
                response
                if return_raw_response
                else (
                    await response.json()
                    if return_json
                    else (
                        raw_text
                        if return_raw_text
                        else (
                            self.parse_list_models(model, raw_text)
                            if is_list
                            else model.model_validate_json(raw_text) if model else raw_text
                        )
                    )
                )
            )


# Применяем патч
AsyncBaseAPI.request = _request_with_proxy
logger.debug("OctoDiary AsyncBaseAPI.request пропатчен для поддержки SOCKS5 прокси")
