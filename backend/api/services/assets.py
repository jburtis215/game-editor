"""The art a creator has uploaded, and how a builder gets hold of it.

Two problems this solves, both learned from the first Godot build.

**A presigned URL is not an asset reference.** `storage.view_url()` mints links that expire
in an hour — right for a browser rendering a page, wrong for an agent whose build session
outlives the link. The engine conventions currently tell builders to ignore `image_url`
entirely for that reason. So assets get a *durable* address here — `/api/assets/entity/12`
— which the API serves by streaming from S3 on demand. It stays valid as long as the object
does, and it names the design object rather than a storage key, so re-uploading art doesn't
invalidate anything pointing at it.

**A bare image doesn't say how to use it.** A 128x32 PNG might be one wide sprite or four
frames of a one-cell walk cycle, and an agent that guesses wrong stretches a sheet across a
single cell. `sprite` carries that answer, sized in **grid cells** rather than pixels, so it
stays tied to the design's unit (one cell = one game unit) and survives a change of
pixels-per-cell on the engine side.

Uploading remains the only way art gets here — image *generation* is deliberately not part
of this path. Greyboxing stays the builder's first pass either way; these assets are what it
reaches for once the creator has real art to give it.
"""
from __future__ import annotations

from typing import Any

from ..models import Ability, Character, EntityType, Level, Location, Project

# kind -> (model, the field holding the S3 key, does this kind carry sprite metadata)
ASSET_KINDS: dict[str, tuple[Any, str, bool]] = {
    # Sprites: art that gets *drawn into the world*, so it carries geometry.
    "entity": (EntityType, "image_key", True),
    "character": (Character, "image_key", True),
    # Reference art: something the builder looks at rather than draws — a mood board for a
    # place, key art for a level or project, an icon for a verb. No geometry to carry.
    "location": (Location, "image_key", False),
    "level": (Level, "image_key", False),
    "ability": (Ability, "image_key", False),
    "project": (Project, "image_key", False),
}

SPRITE_DEFAULTS: dict[str, Any] = {
    # Footprint: how much space the thing OCCUPIES, in grid cells. Fractional on purpose — a
    # small enemy with a half-cell hitbox is a normal thing to want, and rounding it to whole
    # cells would quietly make every creature tile-sized.
    "cells_wide": 1.0,
    "cells_high": 1.0,
    # Keep the footprint tracking `scale` unless the creator has deliberately separated them.
    # Linked is the default because for most things "looks smaller" and "is smaller" are the
    # same intent, and a hitbox that silently disagrees with the art is the classic platformer
    # bug. Unlink when they should differ — a big scary sprite with a forgiving hitbox.
    "footprint_linked": True,
    "frames": 1,
    "fps": 0,  # 0 = a still image, not an animation
    # A visual multiplier on the drawn art, separate from the footprint above. The footprint
    # is how much space the thing *occupies* (collision, level geometry); scale is how big the
    # art *reads* against the level. A goomba can occupy one cell and be drawn at 0.8 so it
    # sits below the tile line — a purely aesthetic call the creator makes by eye, which is
    # why it is a slider in the level editor rather than a number in a form.
    "scale": 1.0,
}


def normalize_sprite(raw: Any) -> dict[str, Any]:
    """Coerce loose sprite JSON into the four known keys, dropping anything else.

    Mirrors how `characterTraits.ts` and `abilities.ts` treat their JSON: the API stores what
    it's given, and one place decides what the shape means. Values are clamped to sane
    minimums so a zero or a negative can't reach a builder as a divide-by-zero.
    """
    if not isinstance(raw, dict) or not raw:
        return {}
    INT_KEYS = {"frames"}
    # Floors keep a zero or a negative from reaching a builder as a divide-by-zero, an
    # invisible sprite or a zero-area hitbox.
    FLOORS = {"fps": 0.0, "scale": 0.05, "cells_wide": 0.05, "cells_high": 0.05}
    out: dict[str, Any] = {}
    for key, default in SPRITE_DEFAULTS.items():
        value = raw.get(key, default)
        if key == "footprint_linked":
            out[key] = bool(value)
            continue
        try:
            value = int(value) if key in INT_KEYS else float(value)
        except (TypeError, ValueError):
            value = default
        out[key] = max(FLOORS.get(key, 1), value)
        if key in ("scale", "cells_wide", "cells_high"):
            out[key] = round(min(8.0, out[key]), 3)

    # The link is enforced here rather than trusted from the client, so the footprint can
    # never drift from the scale it claims to follow — whichever surface did the writing.
    if out["footprint_linked"]:
        out["cells_wide"] = out["cells_high"] = out["scale"]
    return out


def asset_url(kind: str, object_id: int) -> str:
    """The durable path a builder should fetch. Relative, so it works against whatever host
    the API is served on rather than baking in a base URL that would be wrong somewhere."""
    return f"/api/assets/{kind}/{object_id}"


def _rows_for(project: Project, kind: str) -> list[dict[str, Any]]:
    model, key_field, has_sprite = ASSET_KINDS[kind]
    if kind == "location":
        queryset = model.objects.filter(level__project=project)
    elif kind == "project":
        queryset = model.objects.filter(id=project.id)
    else:
        queryset = model.objects.filter(project=project)

    rows = []
    for obj in queryset:
        if not getattr(obj, key_field, ""):
            continue
        row: dict[str, Any] = {
            "kind": kind,
            "id": obj.id,
            "name": obj.name,
            "url": asset_url(kind, obj.id),
            "purpose": "reference" if kind == "location" else "sprite",
        }
        if has_sprite:
            row["sprite"] = normalize_sprite(getattr(obj, "sprite", None))
        rows.append(row)
    return rows


def list_assets(project: Project) -> dict[str, Any]:
    """Every uploaded asset in a project, with a durable URL and how to use it."""
    assets: list[dict[str, Any]] = []
    for kind in ASSET_KINDS:
        assets.extend(_rows_for(project, kind))
    return {
        "project": {"id": project.id, "name": project.name},
        "count": len(assets),
        "assets": assets,
        "note": (
            "Download each `url` into the engine project as a real file — these are stable "
            "paths, but the build should never depend on fetching one at runtime. `sprite` "
            "is sized in grid cells: cells_wide/cells_high give the footprint in game units, "
            "`frames` is how many animation frames the image holds left-to-right, and `fps` "
            "0 means it is a still. An object with no asset listed here has none — greybox "
            "it and move on."
        ),
    }


def key_prefix(kind: str, obj: Any) -> str:
    """The S3 folder for one object's art.

    Mirrors the existing per-model prefixes (`Characters/Project-1/character-2`) so the
    generic upload route drops files exactly where the older per-model endpoints do, and a
    bucket stays browsable by project.
    """
    project_id = getattr(obj, "project_id", None)
    if kind == "location":
        project_id = obj.level.project_id
    elif kind == "project":
        project_id = obj.id
    folder = {
        "entity": "Entities",
        "character": "Characters",
        "location": "Locations",
        "level": "Levels",
        "ability": "Abilities",
        "project": "Projects",
    }[kind]
    return f"{folder}/Project-{project_id}/{kind}-{obj.id}"
