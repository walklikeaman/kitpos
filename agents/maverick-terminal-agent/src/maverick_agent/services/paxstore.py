from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import time
from typing import Iterable
from urllib.parse import urlencode

import httpx


@dataclass(slots=True)
class PaxstoreClient:
    """
    Verified pieces:
    - query params must include sysKey and timestamp
    - signature header is computed from the query string using HMAC-MD5
    - SDK-Language, SDK-Version and Time-Zone headers are expected by the official SDK

    Intentionally missing from this scaffold:
    - final endpoint paths
    - tenant-specific request bodies
    """

    base_url: str
    api_key: str
    api_secret: str
    time_zone: str = "UTC"
    sdk_language: str = "PYTHON"
    sdk_version: str = "0.1.0"

    def signed_params(self, query_params: Iterable[tuple[str, str]] | None = None) -> tuple[list[tuple[str, str]], dict[str, str]]:
        final_params = list(query_params or [])
        final_params.append(("sysKey", self.api_key))
        final_params.append(("timestamp", str(int(time.time() * 1000))))
        query_string = urlencode(final_params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.md5,
        ).hexdigest().upper()
        headers = {
            "signature": signature,
            "SDK-Language": self.sdk_language,
            "SDK-Version": self.sdk_version,
            "Time-Zone": self.time_zone,
        }
        return final_params, headers

    def request(
        self,
        method: str,
        path: str,
        *,
        query_params: Iterable[tuple[str, str]] | None = None,
        json_body: dict | None = None,
        timeout: float = 15.0,
    ) -> httpx.Response:
        params, headers = self.signed_params(query_params)
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, params=params, headers=headers, json=json_body)
            response.raise_for_status()
            return response

