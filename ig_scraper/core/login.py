"""Login helpers backed by the remote API client.

Provides a synchronous helper for scripts and an async helper used
from async workflows. Both call into `storage.api_client`.
"""

from typing import Optional
import asyncio
from storage import api_client


def login_sync(username: Optional[str], password: Optional[str]) -> bool:
    """Perform a synchronous login using the storage API client sync helper.

    Returns True on success, False otherwise.
    """
    try:
        c = api_client._sync_login()
        return True
    except Exception:
        return False


async def login(username: Optional[str], password: Optional[str]) -> bool:
    """Async login wrapper that uses the async API client.

    Returns True when a token was obtained or the login endpoint succeeded.
    """
    try:
        await api_client.client.login(username=username, password=password)
        # consider success if either token or access_token present
        return bool(api_client.client._access_token or api_client.client._token)
    except Exception:
        return False


def ensure_logged_in(username: Optional[str] = None, password: Optional[str] = None) -> bool:
    """Convenience wrapper to run `login` from synchronous code."""
    try:
        return asyncio.run(login(username, password))
    except Exception:
        return False
