"""The design manifest — a map of the game, not a route through it.

One line per design object: its address, a one-phrase summary, its content hash, and the
things it genuinely depends on. Small enough that a building agent can always read it
first, and complete enough to decide what to pull in full afterwards.

The dependency edges here are **entailments of what the designer authored**, never our
opinion about build order: a door locked by `item_cellar_key` cannot be opened before
something grants that key; an ability gated on a state variable needs it declared first; a
scene needs the characters it casts. An agent (or a creator directing one) can derive an
order from these facts, and is free to choose a different one — which is why this is a map
rather than a sequence. Deciding that "health builds before combat" is not ours to make.

Built by reducing the blueprint document, so it can never disagree with what the read tools
serve. That means assembling the full export to produce the summary; fine at prototype
scale, and the note in docs/blueprint-schema.md flags it if that stops being true.
"""
from __future__ import annotations

from typing import Any

from ..models import Project
from . import addressing, blueprint


def _requirement_states(requirements: Any) -> list[str]:
    """The state addresses a bounded-vocabulary requirement list reads."""
    out = []
    for req in requirements or []:
        if isinstance(req, dict) and req.get("state_key"):
            out.append(addressing.state_address(req["state_key"]))
    return out


def _effect_states(effects: Any) -> list[str]:
    """The state addresses an effect list writes — the other half of a lock-and-key pair."""
    out = []
    for effect in effects or []:
        if isinstance(effect, dict) and effect.get("state_key"):
            out.append(addressing.state_address(effect["state_key"]))
    return out


def _dedupe(values: list[str]) -> list[str]:
    seen, out = set(), []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _entity_summary(entity: dict) -> str:
    behavior = entity.get("behavior") or {}
    bits = [entity.get("category") or "entity"]
    if behavior.get("pattern"):
        bits.append(behavior["pattern"])
    if behavior.get("speed") is not None:
        bits.append(f"speed {behavior['speed']}")
    if behavior.get("stompable"):
        bits.append("stompable")
    if behavior.get("harmful_on_touch"):
        bits.append("harmful on touch")
    return " · ".join(str(b) for b in bits)


def _level_summary(level: dict) -> str:
    layout = level.get("layout") or {}
    bits = []
    bits.append(
        f"{layout['width']}x{layout['height']} grid" if layout.get("width") else "no layout drawn"
    )
    if level.get("locations"):
        bits.append(f"{len(level['locations'])} location(s)")
    if level.get("scenes"):
        bits.append(f"{len(level['scenes'])} scene(s)")
    return " · ".join(bits)


def _location_summary(location: dict) -> str:
    bits = [b for b in (location.get("kind"), location.get("scale"), location.get("mood")) if b]
    exits = len(location.get("connections") or [])
    if exits:
        bits.append(f"{exits} exit(s)")
    return " · ".join(bits) or "no detail set"


def build_manifest(project: Project) -> dict[str, Any]:
    """Every design object with its address, hash, summary and real dependencies."""
    doc = blueprint.build_blueprint(project)
    objects: list[dict[str, Any]] = []

    # Which dialogue node grants each state variable — the "key" half of lock-and-key, and
    # the only reason a gated object has anything to wait for.
    granted_by: dict[str, list[str]] = {}
    for level in doc.get("levels") or []:
        for scene in level.get("scenes") or []:
            for node in (scene.get("dialogue") or {}).get("nodes") or []:
                for state in _effect_states(node.get("effects")):
                    granted_by.setdefault(state, []).append(scene["address"])

    for system_id, system in (doc.get("systems") or {}).items():
        if not system.get("enabled"):
            continue
        objects.append(
            {
                "address": system["address"],
                "name": system_id,
                "kind": "system",
                "hash": system["hash"],
                # The plain-language takeaway is the single highest-signal fact about a
                # system, so it rides in the index rather than requiring a pull.
                "summary": (system.get("derived") or {}).get("takeaway", ""),
                "depends_on": [],
            }
        )

    for ability in doc.get("abilities") or []:
        objects.append(
            {
                "address": ability["address"],
                "name": ability["name"],
                "kind": "ability",
                "hash": ability["hash"],
                "summary": ability.get("description") or "",
                # An ability locked behind a state variable can't be granted before it exists.
                "depends_on": _dedupe(_requirement_states(ability.get("unlock_requirements"))),
            }
        )

    for character in doc.get("characters") or []:
        objects.append(
            {
                "address": character["address"],
                "name": character["name"],
                "kind": "character",
                "hash": character["hash"],
                "summary": (character.get("description") or "").split("\n")[0][:120],
                "depends_on": [],
            }
        )

    for entity in doc.get("entity_types") or []:
        objects.append(
            {
                "address": entity["address"],
                "name": entity["name"],
                "kind": "entity",
                "glyph": entity.get("glyph"),
                "hash": entity["hash"],
                "summary": _entity_summary(entity),
                "depends_on": [],
            }
        )

    for state_key, entry in (doc.get("state_schema") or {}).items():
        address = entry.get("address") or addressing.state_address(state_key)
        objects.append(
            {
                "address": address,
                "name": entry.get("label") or state_key,
                "kind": "state",
                "hash": addressing.content_hash(entry),
                "summary": entry.get("type") or "",
                "depends_on": [],
                # Not a dependency of its own, but the fact a gated object needs: this is
                # where the key comes from.
                "granted_by": _dedupe(granted_by.get(address, [])),
            }
        )

    glyph_to_entity = {
        e.get("glyph"): e["address"] for e in doc.get("entity_types") or [] if e.get("glyph")
    }
    for level in doc.get("levels") or []:
        scenes_by_id = {s["id"]: s for s in level.get("scenes") or []}
        used_glyphs = {ch for row in (level.get("layout") or {}).get("rows") or [] for ch in row}
        level_deps = [glyph_to_entity[g] for g in sorted(used_glyphs) if g in glyph_to_entity]
        intro = scenes_by_id.get(level.get("intro_scene_id"))
        if intro:
            level_deps.append(intro["address"])
        objects.append(
            {
                "address": level["address"],
                "name": level["name"],
                "kind": "level",
                "order": level.get("order"),
                "hash": level["hash"],
                "summary": _level_summary(level),
                "next_level": None,
                # A level needs the entity types its grid places, and its intro scene.
                "depends_on": _dedupe(level_deps),
            }
        )

        for location in level.get("locations") or []:
            deps = []
            for connection in location.get("connections") or []:
                deps += _requirement_states(connection.get("requirements"))
            objects.append(
                {
                    "address": location["address"],
                    "name": location["name"],
                    "kind": "location",
                    "level": level["address"],
                    "hash": location["hash"],
                    "summary": _location_summary(location),
                    # A locked exit can't be walked before the key exists.
                    "depends_on": _dedupe(deps),
                }
            )

        for scene in level.get("scenes") or []:
            nodes = (scene.get("dialogue") or {}).get("nodes") or []
            speakers = _dedupe(
                [n["speaker"] for n in nodes if n.get("speaker")]
            )
            by_name = {c["name"]: c["address"] for c in doc.get("characters") or []}
            deps = [by_name[s] for s in speakers if s in by_name]
            for node in nodes:
                deps += _requirement_states(node.get("requirements"))
            objects.append(
                {
                    "address": scene["address"],
                    "name": scene["name"],
                    "kind": "scene",
                    "level": level["address"],
                    "is_intro": scene.get("is_intro", False),
                    "hash": scene["hash"],
                    "summary": f"{len(nodes)} dialogue node(s)",
                    # A scene needs the characters it casts, and any state its choices read.
                    "depends_on": _dedupe(deps),
                }
            )

    # Level ordering is a fact the designer set, not a build opinion — record it as the
    # transition it is, rather than as a step number.
    levels = [o for o in objects if o["kind"] == "level"]
    by_id = {level["id"]: level for level in doc.get("levels") or []}
    for entry, level in zip(levels, doc.get("levels") or []):
        next_id = (level.get("on_complete") or {}).get("next_level_id")
        if next_id in by_id:
            entry["next_level"] = by_id[next_id]["address"]

    counts: dict[str, int] = {}
    for obj in objects:
        counts[obj["kind"]] = counts.get(obj["kind"], 0) + 1

    return {
        "format": blueprint.FORMAT,
        "project": {**doc["project"], "hash": doc["hash"]},
        "counts": counts,
        "objects": objects,
    }
