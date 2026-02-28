import asyncio
import logging
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE", "http://localhost:5000").rstrip("/")
API_USER = os.getenv("API_USER", "")
API_PASS = os.getenv("API_PASS", "")
API_CLIENT_ID = os.getenv("API_CLIENT_ID", "Lens_App")
API_SCOPE = os.getenv("API_SCOPE", "Lens")

logger = logging.getLogger("ig_scraper.api_client")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s [api_client] %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class APIClient:
    def __init__(self) -> None:
        self.base = API_BASE
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expiry: float | None = None
        self._lock = asyncio.Lock()
        self._max_retries = 3
        self._backoff_factor = 0.5

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base, timeout=30.0)
        if not self._has_valid_token():
            await self.login()

    def _has_valid_token(self) -> bool:
        if not self._access_token:
            return False
        if not self._token_expiry:
            return True
        return time.time() < (self._token_expiry - 30)

    @staticmethod
    def _parse_json_safe(resp: httpx.Response | None) -> Any:
        if resp is None:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    async def _request_with_retries(self, method: str, url: str, **kwargs) -> httpx.Response | None:
        await self._ensure_client()
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                assert self._client is not None
                resp = await self._client.request(method, url, follow_redirects=True, **kwargs)
                logger.info("%s %s -> %d", method.upper(), url, resp.status_code)
                return resp
            except Exception as exc:
                last_exc = exc
                sleep_for = self._backoff_factor * (2 ** (attempt - 1))
                logger.warning(
                    "Request failed %s %s attempt %d: %s; retrying in %.2fs",
                    method.upper(),
                    url,
                    attempt,
                    exc,
                    sleep_for,
                )
                await asyncio.sleep(sleep_for)

        logger.error("Request ultimately failed: %s %s: %s", method.upper(), url, last_exc)
        return None

    async def login(self, username: str | None = None, password: str | None = None) -> bool:
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(base_url=self.base, timeout=30.0)

            if self._has_valid_token():
                return True

            resolved_username = username or API_USER
            resolved_password = password or API_PASS
            if not resolved_username or not resolved_password:
                logger.error("Missing API credentials. Set API_USER and API_PASS in environment.")
                return False

            form_payload = {
                "grant_type": "password",
                "username": resolved_username,
                "password": resolved_password,
                "client_id": API_CLIENT_ID,
                "scope": API_SCOPE,
            }
            token_resp = await self._client.post(
                "/connect/token",
                data=form_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=True,
            )

            token_json = self._parse_json_safe(token_resp)
            token = token_json.get("access_token") if isinstance(token_json, dict) else None
            expires = token_json.get("expires_in") if isinstance(token_json, dict) else None

            if token:
                self._access_token = token
                try:
                    self._token_expiry = time.time() + int(expires)
                except Exception:
                    self._token_expiry = None
                self._client.headers.update({"Authorization": f"Bearer {token}"})
                logger.info("Obtained OAuth access token")
                return True

            logger.error("Failed to fetch OAuth token from /connect/token")
            return False

    async def _get_all_paged_items(
        self,
        path: str,
        base_params: dict[str, Any] | None = None,
        total_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params = dict(base_params or {})
        max_result_count = int(params.pop("MaxResultCount", 200))
        skip_count = int(params.pop("SkipCount", 0))

        items: list[dict[str, Any]] = []
        total_count = None

        while True:
            query = {
                **params,
                "SkipCount": skip_count,
                "MaxResultCount": max_result_count,
            }
            resp = await self._request_with_retries("get", path, params=query)
            data = self._parse_json_safe(resp)
            if not isinstance(data, dict):
                break

            page_items = data.get("items")
            if not isinstance(page_items, list):
                break

            items.extend([x for x in page_items if isinstance(x, dict)])

            if total_limit and len(items) >= total_limit:
                return items[:total_limit]

            if total_count is None:
                total_count = data.get("totalCount") if isinstance(data.get("totalCount"), int) else None

            if not page_items:
                break

            skip_count += len(page_items)
            if total_count is not None and skip_count >= total_count:
                break

        return items

    async def fetch_sources(
        self,
        platform: int | None = None,
        is_active: bool = True,
        max_result_count: int = 200,
        total_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"IsActive": is_active, "MaxResultCount": max_result_count}
        if platform is not None:
            params["Platform"] = platform
        return await self._get_all_paged_items("/api/app/source", params, total_limit=total_limit)

    async def get_recent_post_ids(self, source_id: str, limit: int = 50) -> set[str]:
        if not source_id:
            return set()

        resp = await self._request_with_retries(
            "get",
            "/api/app/scraper/posts",
            params={
                "SourceId": source_id,
                "SkipCount": 0,
                "MaxResultCount": max(1, min(limit, 200)),
            },
        )
        data = self._parse_json_safe(resp)
        if not isinstance(data, dict):
            return set()

        items = data.get("items")
        if not isinstance(items, list):
            return set()

        post_ids: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            external_post_id = item.get("externalPostId")
            if isinstance(external_post_id, str) and external_post_id:
                post_ids.add(external_post_id)
        return post_ids

    async def write_posts(self, posts: list[dict[str, Any]]) -> Any:
        if not posts:
            return {"items": []}
        resp = await self._request_with_retries("put", "/api/app/scraper/posts", json=posts)
        return self._parse_json_safe(resp)

    async def post_exists(self, source_id: str, external_post_id: str) -> bool:
        if not source_id or not external_post_id:
            return False

        resp = await self._request_with_retries(
            "get",
            "/api/app/scraper/posts",
            params={
                "SourceId": source_id,
                "ExternalPostId": external_post_id,
                "SkipCount": 0,
                "MaxResultCount": 1,
            },
        )
        data = self._parse_json_safe(resp)
        if not isinstance(data, dict):
            return False

        total_count = data.get("totalCount")
        if isinstance(total_count, int):
            return total_count > 0

        items = data.get("items")
        return isinstance(items, list) and len(items) > 0

    async def write_profile(self, profile: dict[str, Any]) -> Any:
        resp = await self._request_with_retries("put", "/api/app/profiles", json=profile)
        return self._parse_json_safe(resp)

    async def record_baseline(self, selector: str, hash_value: str, last_seen: str | None = None) -> Any:
        payload = {"selector": selector, "hash": hash_value, "lastSeen": last_seen}
        resp = await self._request_with_retries("put", "/api/app/baselines", json=payload)
        return self._parse_json_safe(resp)

    async def record_post_history(self, entry: dict[str, Any]) -> Any:
        resp = await self._request_with_retries("put", "/api/app/post_history", json=entry)
        return self._parse_json_safe(resp)

    async def check_cooldown(self, username: str) -> Any:
        resp = await self._request_with_retries("get", "/api/app/cooldowns", params={"username": username})
        return self._parse_json_safe(resp)

    async def set_cooldown(self, username: str, hours: int = 24) -> Any:
        payload = {"username": username, "hours": hours}
        resp = await self._request_with_retries("put", "/api/app/cooldowns", json=payload)
        return self._parse_json_safe(resp)


client = APIClient()


async def fetch_sources(
    platform: int | None = None,
    is_active: bool = True,
    max_result_count: int = 200,
    total_limit: int | None = None,
):
    return await client.fetch_sources(
        platform=platform,
        is_active=is_active,
        max_result_count=max_result_count,
        total_limit=total_limit,
    )


async def write_posts(posts: list[dict[str, Any]]):
    return await client.write_posts(posts)


async def post_exists(source_id: str, external_post_id: str):
    return await client.post_exists(source_id, external_post_id)


async def get_recent_post_ids(source_id: str, limit: int = 50):
    return await client.get_recent_post_ids(source_id, limit=limit)


async def write_profile(profile: dict[str, Any]):
    return await client.write_profile(profile)


async def record_baseline(selector: str, hash_value: str, last_seen: str | None = None):
    return await client.record_baseline(selector, hash_value, last_seen)


async def record_post_history(entry: dict[str, Any]):
    return await client.record_post_history(entry)


async def check_cooldown(username: str):
    return await client.check_cooldown(username)


async def set_cooldown_api(username: str, hours: int = 24):
    return await client.set_cooldown(username, hours)


def _sync_login() -> httpx.Client:
    c = httpx.Client(base_url=API_BASE, timeout=20.0)
    r = c.post(
        "/connect/token",
        data={
            "grant_type": "password",
            "username": API_USER,
            "password": API_PASS,
            "client_id": API_CLIENT_ID,
            "scope": API_SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    token = None
    try:
        token = r.json().get("access_token")
    except Exception:
        token = None
    if not token:
        raise RuntimeError("Unable to obtain access_token from /connect/token")
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload, list):
        return payload
    return []


def fetch_profiles_sync():
    with _sync_login() as c:
        r = c.get("/api/app/profiles", params={"MaxResultCount": 200})
        if r.status_code >= 400:
            return []
        try:
            return _extract_items(r.json())
        except Exception:
            return []


def fetch_posts_sync():
    with _sync_login() as c:
        r = c.get("/api/app/scraper/posts", params={"MaxResultCount": 200})
        if r.status_code >= 400:
            return []
        try:
            return _extract_items(r.json())
        except Exception:
            return []


def fetch_post_history_sync():
    with _sync_login() as c:
        r = c.get("/api/app/post_history", params={"MaxResultCount": 200})
        if r.status_code >= 400:
            return []
        try:
            return _extract_items(r.json())
        except Exception:
            return []
