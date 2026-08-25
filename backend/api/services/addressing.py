"""Addresses and content hashes for design objects.

Two separate ideas that the build loop both depends on:

**Addresses** are names. `entity:goomba` is the one word the platform, the creator and a
building agent all use for the same thing — readable, and the same string in a Godot
filename as in a report back to the platform. An address is derived from the object's own
name, so it follows renames (see `DesignAddress` for why that is deliberate); the object's
numeric id remains its identity, and a building agent should key its own records on the id
so a rename it hasn't caught up with can never orphan anything.

**Hashes** are versions. Each object's hash fingerprints its slice of the export, so a
build reported against hash `a3f19c` can be recognised as stale once the designer edits it.
Content hashing (rather than `updated_at`) matters in this codebase specifically: the
editor debounce-saves while a slider is being dragged, so timestamps churn constantly while
the design does not actually change.

Addresses are assigned lazily, while the export or manifest is built — nothing needs one
before something reads the design.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..models import DesignAddress, Project

# Address types that are backed by a row and can therefore be renamed. Types whose name is
# already a stable key — `system:movement`, `state:item_key`, `dialogue:<title>` — are
# formatted directly by the helpers at the bottom and never need a DesignAddress row.
RENAMEABLE_TYPES = DesignAddress.OBJECT_TYPES


def slugify(value: str, fallback: str = "unnamed") -> str:
    """Snake_case a name into an address slug. Matches the rule used by `Dialogue._slugify`
    and the frontend's `traitKey()`, so every readable key in the system looks the same."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return slug or fallback


def _base_of(slug: str) -> str:
    """`goomba_2` -> `goomba`. Used to tell a collision-suffixed address apart from a
    genuine rename, so re-exporting an object whose name never changed is a no-op."""
    return re.sub(r"_\d+$", "", slug)


def _unique_slug(project_id: int, object_type: str, desired: str, object_id: int) -> str:
    taken = set(
        DesignAddress.objects.filter(
            project_id=project_id, object_type=object_type, is_current=True
        )
        .exclude(object_id=object_id)
        .values_list("slug", flat=True)
    )
    if desired not in taken:
        return desired
    n = 2
    while f"{desired}_{n}" in taken:
        n += 1
    return f"{desired}_{n}"


def ensure_address(project_id: int, object_type: str, object_id: int, name: str) -> str:
    """The object's current address, assigning or updating the row as needed.

    Keeps the existing slug when the name still produces it (allowing for a `_2` collision
    suffix), so exporting repeatedly is stable. When the name really has changed, the old
    row is retired rather than deleted — references an agent wrote down earlier still
    resolve through `resolve()`.
    """
    desired = slugify(name, fallback=object_type)
    current = DesignAddress.objects.filter(
        project_id=project_id,
        object_type=object_type,
        object_id=object_id,
        is_current=True,
    ).first()

    if current is not None:
        if _base_of(current.slug) == desired:
            return current.address
        current.is_current = False
        current.save(update_fields=["is_current"])

    slug = _unique_slug(project_id, object_type, desired, object_id)
    # A retired row for this same object and slug may already exist (the designer renamed
    # away and back again); revive it instead of stacking duplicates.
    revived = DesignAddress.objects.filter(
        project_id=project_id, object_type=object_type, object_id=object_id, slug=slug
    ).first()
    if revived is not None:
        revived.is_current = True
        revived.save(update_fields=["is_current"])
        return revived.address

    return DesignAddress.objects.create(
        project_id=project_id, object_type=object_type, object_id=object_id, slug=slug
    ).address


def former_addresses(project_id: int, object_type: str, object_id: int) -> list[str]:
    """Every address this object used to have, oldest first — so a rename is visible to a
    consumer holding a stale reference."""
    return [
        row.address
        for row in DesignAddress.objects.filter(
            project_id=project_id,
            object_type=object_type,
            object_id=object_id,
            is_current=False,
        ).order_by("created_at", "id")
    ]


def resolve(project: Project, address: str) -> dict[str, Any] | None:
    """Look up an address, including one that has since been renamed away.

    Returns `{object_type, object_id, address, current, renamed_from}` — `current` is the
    address the object answers to now, so a caller holding an old reference learns both
    that it still resolves and what to call it going forward. A live address always wins
    over a retired one, so a name freed by a rename and then reused points at the new
    object.
    """
    if ":" not in (address or ""):
        return None
    object_type, _, slug = address.partition(":")
    rows = DesignAddress.objects.filter(
        project=project, object_type=object_type, slug=slug
    ).order_by("-is_current", "-created_at")
    row = rows.first()
    if row is None:
        return None
    if row.is_current:
        return {
            "object_type": row.object_type,
            "object_id": row.object_id,
            "address": address,
            "current": address,
            "renamed_from": None,
        }
    live = DesignAddress.objects.filter(
        project=project,
        object_type=row.object_type,
        object_id=row.object_id,
        is_current=True,
    ).first()
    if live is None:
        return None
    return {
        "object_type": live.object_type,
        "object_id": live.object_id,
        "address": address,
        "current": live.address,
        "renamed_from": address,
    }


# --- Addresses for the types that don't need a row --------------------------------------


def system_address(system_id: str) -> str:
    """`system:movement`. A system's id is defined in code (`gameSystems.ts`), not typed by
    the creator, so it is already stable and never renames."""
    return f"system:{system_id}"


def state_address(state_key: str) -> str:
    """`state:item_cellar_key`. The state key *is* the name — the dialogue editor mints it
    once from the effect's label and everything references it by key thereafter."""
    return f"state:{state_key}"


def dialogue_address(title: str) -> str:
    """`dialogue:opening_1`. Reuses `Dialogue.title`, which is already a persisted,
    Yarn-friendly identifier generated at creation."""
    return f"dialogue:{title}"


def project_address(name: str) -> str:
    return f"project:{slugify(name, fallback='project')}"


# --- Hashing ----------------------------------------------------------------------------

HASH_LENGTH = 8


def content_hash(payload: Any) -> str:
    """A short, stable fingerprint of one object's exported slice.

    Canonical JSON (sorted keys, no incidental whitespace) so the same design always
    produces the same hash regardless of dict ordering. Truncated because these are read
    and compared by humans and agents, not used as security digests.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:HASH_LENGTH]


def rollup_hash(hashes: list[str]) -> str:
    """One hash standing for a whole collection — lets "has anything changed?" be a single
    comparison instead of a walk."""
    return content_hash(sorted(hashes))
