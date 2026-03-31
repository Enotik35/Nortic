import json
from typing import Any

import httpx


class ThreeXUIError(Exception):
    pass


class ThreeXUIAuthError(ThreeXUIError):
    pass


class ThreeXUIProvider:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        self._client = httpx.AsyncClient(
            base_url=self.base_url + "/",
            verify=self.verify_ssl,
            timeout=self.timeout,
            follow_redirects=True,
        )
        self._is_logged_in = False

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self) -> None:
        response = await self._client.post(
            "login",
            data={
                "username": self.username,
                "password": self.password,
                "twoFactorCode": "",
            },
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            raise ThreeXUIAuthError(
                f"3x-ui login failed with status {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except Exception:
            data = None

        if isinstance(data, dict) and data.get("success") is False:
            raise ThreeXUIAuthError(f"3x-ui login failed: {data.get('msg') or data}")

        self._is_logged_in = True

    async def ensure_login(self) -> None:
        if not self._is_logged_in:
            await self.login()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        form_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self.ensure_login()

        response = await self._client.request(
            method,
            path.lstrip("/"),
            json=json_body,
            data=form_body,
            headers={"Accept": "application/json"},
        )

        if response.status_code == 404:
            raise ThreeXUIError(
                f"3x-ui returned 404 for path '{path}'. "
                "Проверьте THREEXUI_BASE_URL и путь API."
            )

        if response.status_code >= 400:
            raise ThreeXUIError(
                f"3x-ui request failed: {response.status_code} {response.text}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise ThreeXUIError(
                f"3x-ui returned non-JSON response: {response.text}"
            ) from exc

        if isinstance(data, dict) and data.get("success") is False:
            raise ThreeXUIError(f"3x-ui API error: {data.get('msg') or data}")

        return data

    async def get_inbound(self, inbound_id: int) -> dict[str, Any]:
        return await self._request("GET", f"panel/api/inbounds/get/{inbound_id}")

    async def list_inbounds(self) -> dict[str, Any]:
        return await self._request("GET", "panel/api/inbounds/list")

    async def add_vless_client(
        self,
        *,
        inbound_id: int,
        client_id: str,
        email: str,
        flow: str = "xtls-rprx-vision",
        limit_ip: int = 0,
        total_gb: int = 0,
        expiry_time_ms: int = 0,
        enable: bool = True,
        tg_id: str = "",
        sub_id: str = "",
        comment: str = "",
        reset: int = 0,
    ) -> dict[str, Any]:
        client_payload = {
            "id": client_id,
            "flow": flow,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb,
            "expiryTime": expiry_time_ms,
            "enable": enable,
            "tgId": tg_id,
            "subId": sub_id,
            "comment": comment,
            "reset": reset,
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_payload]}, ensure_ascii=False),
        }

        return await self._request(
            "POST",
            "panel/api/inbounds/addClient",
            form_body=payload,
        )

    async def update_vless_client(
        self,
        *,
        client_id: str,
        email: str,
        inbound_id: int,
        flow: str = "xtls-rprx-vision",
        limit_ip: int = 0,
        total_gb: int = 0,
        expiry_time_ms: int = 0,
        enable: bool = True,
        tg_id: str = "",
        sub_id: str = "",
        comment: str = "",
        reset: int = 0,
    ) -> dict[str, Any]:
        client_payload = {
            "id": client_id,
            "flow": flow,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_gb,
            "expiryTime": expiry_time_ms,
            "enable": enable,
            "tgId": tg_id,
            "subId": sub_id,
            "comment": comment,
            "reset": reset,
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_payload]}, ensure_ascii=False),
        }

        return await self._request(
            "POST",
            f"panel/api/inbounds/updateClient/{client_id}",
            form_body=payload,
        )

    async def delete_vless_client(
        self,
        *,
        inbound_id: int,
        client_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"panel/api/inbounds/{inbound_id}/delClient/{client_id}",
        )

    async def delete_vless_client_by_email(
        self,
        *,
        inbound_id: int,
        email: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"panel/api/inbounds/{inbound_id}/delClientByEmail/{email}",
        )
