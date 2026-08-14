"""AI character-image generation via FLUX (Black Forest Labs), hosted on fal.ai.

We call fal.ai's synchronous run endpoint for a FLUX model, which returns a hosted image URL; we
download the bytes and hand them back so the caller can store them in *our* S3 (fal's URLs are
temporary). Swapping providers (Replicate, BFL direct, Stability, OpenAI, …) only means changing
this file — the contract `generate_image(prompt) -> (bytes, content_type)` stays the same.

While `FAL_KEY` is blank or still a REPLACE_ME placeholder, `is_configured()` is False and callers
should surface a "not configured" message rather than calling out.
"""
from __future__ import annotations

import requests
from django.conf import settings

_PLACEHOLDER = "REPLACE_ME"
_TIMEOUT = 120  # generation + download can be slow


class GenerationNotConfigured(Exception):
    """The fal.ai API key isn't set up yet."""


class GenerationError(Exception):
    """The generation request failed or returned no image."""


def _is_set(value: str) -> bool:
    return bool(value) and _PLACEHOLDER not in value


def is_configured() -> bool:
    return _is_set(settings.FAL_KEY)


def generate_image(prompt: str) -> tuple[bytes, str]:
    """Generate an image for `prompt` and return (image_bytes, content_type).

    Uses fal.ai's synchronous endpoint (`https://fal.run/<model>`), which blocks until the image
    is ready and returns JSON with an `images[].url`. FLUX dev/schnell finish in a few seconds; if
    you switch to a slower/higher-quality model and hit gateway timeouts, move to fal's queue API
    (`https://queue.fal.run/<model>` — submit, poll the status_url, then fetch the result).
    """
    if not is_configured():
        raise GenerationNotConfigured(
            "AI image generation is not configured. Set FAL_KEY in backend/.env "
            "(get a key at https://fal.ai/dashboard/keys)."
        )
    headers = {
        "Authorization": f"Key {settings.FAL_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "image_size": "square_hd",  # 1024×1024 — suits the round/square character frames
        "num_images": 1,
        "output_format": "jpeg",
        "enable_safety_checker": True,
    }
    try:
        resp = requests.post(
            f"https://fal.run/{settings.FAL_IMAGE_MODEL}",
            headers=headers,
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        images = (resp.json() or {}).get("images") or []
        if not images or not images[0].get("url"):
            raise GenerationError("Generation response did not include an image.")
        img = requests.get(images[0]["url"], timeout=_TIMEOUT)
        img.raise_for_status()
    except requests.RequestException as exc:
        raise GenerationError(f"FLUX request failed: {exc}") from exc
    content_type = img.headers.get("Content-Type") or images[0].get("content_type") or "image/jpeg"
    return img.content, content_type


def default_prompt(name: str, description: str) -> str:
    """A sensible default prompt built from the character's name + description.

    The trailing style layer keeps a whole cast looking like one game — tune it (or eventually
    drive it from the project's genre/art direction) for a consistent look.
    """
    base = f"character portrait of {name}" if name else "character portrait"
    if description:
        base += f", {description}"
    return (
        f"{base}, painterly RPG concept art, dramatic rim lighting, "
        "centered bust, neutral background, highly detailed"
    )


def default_location_prompt(
    name: str, description: str, *, mood: str = "", kind: str = "", scale: str = ""
) -> str:
    """A default prompt for a location's reference image, built from its detail fields.

    The location half of `default_prompt` — same style layer so places and characters read
    as one game. `mood`/`kind`/`scale` are the Locations page's detail fields; each is
    optional and simply dropped when unset.
    """
    base = f"environment concept art of {name}" if name else "environment concept art"
    qualifiers = ", ".join(part for part in (kind, f"{scale} space" if scale else "") if part)
    if qualifiers:
        base += f", {qualifiers}"
    if description:
        base += f", {description}"
    if mood:
        base += f", mood: {mood}"
    return (
        f"{base}, painterly RPG concept art, establishing wide shot, "
        "atmospheric lighting, no characters, highly detailed"
    )
