"""Thin async HTTP wrapper around the game-editor REST API.

The MCP server sits *on top of* the Django Ninja API (mounted at /api) rather than
importing Django — so it stays a plain client, works against a remote deployment, and
can never bypass the validation the endpoints already do.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

API_URL = os.getenv("GAME_EDITOR_API_URL", "http://127.0.0.1:8000/api").rstrip("/")

_client: httpx.AsyncClient | None = None


class ApiError(RuntimeError):
    """An API call failed — the message is written to be read by an agent."""


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=API_URL, timeout=120.0)
    return _client


def _drop_none(data: dict[str, Any] | None) -> dict[str, Any]:
    """Omit unset values so PATCHes stay partial (the API treats absent as 'unchanged')."""
    return {k: v for k, v in (data or {}).items() if v is not None}


async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    try:
        response = await _get_client().request(
            method, path, params=_drop_none(params), json=_drop_none(json)
        )
    except httpx.RequestError as exc:
        raise ApiError(
            f"Could not reach the game-editor API at {API_URL} ({exc}). "
            "Start the backend with `npm run dev:api` (or set GAME_EDITOR_API_URL)."
        ) from exc

    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = body.get("error") or body.get("detail") or str(body)
        except ValueError:
            detail = response.text[:400]
        raise ApiError(f"{method} {path} failed ({response.status_code}): {detail}")

    if response.status_code == 204 or not response.content:
        return None
    return response.json()


async def get(path: str, **params: Any) -> Any:
    return await request("GET", path, params=params)


async def post(path: str, **json: Any) -> Any:
    return await request("POST", path, json=json)


async def patch(path: str, **json: Any) -> Any:
    return await request("PATCH", path, json=json)


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
