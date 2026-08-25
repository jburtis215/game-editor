"""Build the unified project export — the `gameblueprint/0.1` document.

This is the platform's single source-of-truth artifact: everything a downstream consumer
(an AI coding agent via the MCP server, an engine codegen script, or a human) needs to
build the game. Served by GET /api/projects/{id}/export; the schema contract is documented
in docs/blueprint-schema.md — update BOTH when changing shapes, and bump FORMAT on any
breaking change.
"""
from typing import Any

from ..models import DialogueEdge, EntityType, Level, Project
from . import addressing, derived, storage, yarn_export

FORMAT = "gameblueprint/0.1"

# Glyphs with fixed meanings in every Level.layout. EntityType glyphs may not collide.
BUILTIN_TILES: dict[str, str] = {
    ".": "empty space",
    "#": "solid ground (collidable from all sides)",
    "=": "one-way platform (collidable from above only)",
    "P": "player start position",
    "G": "goal — touching it completes the level",
}


def _entities_from_layout(layout: dict, glyph_to_entity: dict[str, EntityType]) -> list[dict]:
    """Derive a coordinate list from the ASCII rows. (0,0) is the TOP-LEFT cell;
    y increases downward (row index), x increases rightward (column index)."""
    out: list[dict] = []
    for y, row in enumerate(layout.get("rows") or []):
        for x, glyph in enumerate(row):
            if glyph in BUILTIN_TILES:
                if glyph in ("P", "G"):
                    out.append({"glyph": glyph, "builtin": True, "x": x, "y": y})
            elif glyph in glyph_to_entity:
                out.append(
                    {"glyph": glyph, "entity_type_id": glyph_to_entity[glyph].id, "x": x, "y": y}
                )
            else:
                out.append({"glyph": glyph, "unknown": True, "x": x, "y": y})
    return out


# Yarn variable defaults per state_schema type. Booleans for the three flag-ish kinds,
# a number for stats — matching what `yarn_export._effect_lines` writes into them.
_DECLARE_DEFAULTS: dict[str, str] = {
    "flag": "false",
    "remembered_choice": "false",
    "item": "false",
    "stat": "0",
}


def _yarn_declarations(state_schema: dict) -> str:
    """One `<<declare>>` block for the whole project.

    `yarn_export` deliberately omits declares per scene: scenes share state keys, and
    declaring the same variable in two `.yarn` files is a Yarn Spinner compile error.
    Emitting them once at project level is the resolution — write this block to a single
    `variables.yarn` (or equivalent) and the per-scene exports drop in beside it.
    """
    lines = []
    for key, entry in sorted((state_schema or {}).items()):
        if not isinstance(entry, dict):
            continue
        default = _DECLARE_DEFAULTS.get(entry.get("type"), "false")
        label = (entry.get("label") or "").strip()
        comment = f"  // {label}" if label else ""
        lines.append(f"<<declare ${key} = {default}>>{comment}")
    return "\n".join(lines)


def _resolved_traits(character, project_defaults: list[dict]) -> list[dict]:
    """A character's effective traits: project defaults overlaid with the character's own.

    Mirrors `resolveTraits()` in frontend/src/lib/characterTraits.ts — project defaults
    first, then traits only this character has; first definition of a key wins, and the
    stored value falls back to the definition's default.
    """
    stored = character.traits if isinstance(character.traits, dict) else {}
    values = stored.get("values") if isinstance(stored.get("values"), dict) else {}
    own = stored.get("own") if isinstance(stored.get("own"), list) else []

    out: list[dict] = []
    seen: set[str] = set()
    for source, defs in (("project", project_defaults), ("own", own)):
        for definition in defs:
            if not isinstance(definition, dict):
                continue
            key = definition.get("key")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(
                {**definition, "value": values.get(key, definition.get("default")), "source": source}
            )
    return out


def _connections_for(location) -> list[dict]:
    """Every exit walkable from this location, described relative to it. Mirrors the
    same-named helper in api.py: edges authored here, plus bidirectional edges authored
    from the far end (a one-way edge appears only on its source)."""
    out = []
    for conn, from_here in [(c, True) for c in location.connections_out.all()] + [
        (c, False) for c in location.connections_in.all() if c.bidirectional
    ]:
        other = conn.to_location if from_here else conn.from_location
        out.append(
            {
                "id": conn.id,
                "other_id": other.id,
                "other_name": other.name,
                "direction": "out" if from_here else "in",
                "label": conn.label,
                "bidirectional": conn.bidirectional,
                "requirements": conn.requirements or [],
            }
        )
    return out


def _locations_for(level) -> list[dict]:
    """The level's places: detail fields, cast, exits, and the scenes set there."""
    return [
        _addressed(level.project_id, "location", {
            "id": loc.id,
            "name": loc.name,
            "description": loc.description,
            "order": loc.order,
            "kind": loc.kind,
            "scale": loc.scale,
            "mood": loc.mood,
            "props": loc.props or [],
            "image_url": storage.view_url(loc.image_key),
            "characters": [{"id": c.id, "name": c.name} for c in loc.characters.all()],
            "connections": _connections_for(loc),
            "scene_ids": [s.id for s in loc.scenes.all()],
        })
        for loc in level.locations.all()
    ]


def _dialogue_graph(scene) -> dict:
    """A scene's full dialogue graph: flat nodes + explicit edges (with option labels)."""
    nodes = list(scene.dialogues.select_related("character").all())
    node_ids = [n.id for n in nodes]
    edges = DialogueEdge.objects.filter(from_node_id__in=node_ids).order_by("order", "id")
    incoming = {e.to_node_id for e in edges}
    return {
        "nodes": [
            {
                "id": n.id,
                "title": n.title,
                "address": addressing.dialogue_address(n.title),
                "speaker": n.character.name if n.character else None,
                "character_id": n.character_id,
                "text": n.text,
                "requirements": n.requirements or [],
                "effects": n.effects or [],
                "is_root": n.id not in incoming,
            }
            for n in nodes
        ],
        "edges": [
            {
                "from": e.from_node_id,
                "to": e.to_node_id,
                "option_label": e.option_label,
                "order": e.order,
            }
            for e in edges
        ],
    }


def _addressed(project_id: int, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp a serialized object with its address, any former addresses, and its hash.

    The hash covers the payload *including* the address, so a rename shows up as a change —
    which is right: a renamed object needs its engine-side artifact renamed too.
    """
    address = addressing.ensure_address(
        project_id, object_type, payload["id"], payload.get("name") or ""
    )
    out = {**payload, "address": address}
    former = addressing.former_addresses(project_id, object_type, payload["id"])
    if former:
        out["former_addresses"] = former
    out["hash"] = addressing.content_hash(out)
    return out


def build_blueprint(project: Project) -> dict[str, Any]:
    entity_types = list(project.entity_types.all())
    glyph_to_entity = {e.glyph: e for e in entity_types}
    levels = list(
        project.levels.prefetch_related(
            "scenes__dialogues__character",
            "locations__characters",
            "locations__scenes",
            "locations__connections_out__to_location",
            "locations__connections_in__from_location",
        ).all()
    )
    project_trait_defs = [d for d in (project.character_traits or []) if isinstance(d, dict)]

    systems_out: dict[str, Any] = {}
    for sys_id, state in (project.systems or {}).items():
        if not isinstance(state, dict):
            continue
        values = state.get("values") or {}
        entry: dict[str, Any] = {
            "address": addressing.system_address(sys_id),
            "enabled": bool(state.get("enabled")),
            "values": values,
        }
        d = derived.derive_for_system(sys_id, values)
        if d:
            entry["derived"] = d
        entry["hash"] = addressing.content_hash(entry)
        systems_out[sys_id] = entry

    tile_legend: dict[str, str] = dict(BUILTIN_TILES)
    for e in entity_types:
        tile_legend[e.glyph] = f"{e.name} ({e.category})"

    levels_out = []
    for i, level in enumerate(levels):
        next_level = levels[i + 1] if i + 1 < len(levels) else None
        levels_out.append(
            _addressed(project.id, "level", {
                "id": level.id,
                "name": level.name,
                "order": level.order,
                "layout": level.layout or None,
                "entities": _entities_from_layout(level.layout or {}, glyph_to_entity),
                "intro_scene_id": level.intro_scene_id,
                "on_complete": {"next_level_id": next_level.id if next_level else None},
                "locations": _locations_for(level),
                "scenes": [
                    _addressed(project.id, "scene", {
                        "id": s.id,
                        "name": s.name,
                        "order": s.order,
                        "location_id": s.location_id,
                        "is_intro": s.id == level.intro_scene_id,
                        "dialogue": _dialogue_graph(s),
                        "yarn": yarn_export.export_scene_to_yarn(s),
                    })
                    for s in level.scenes.all()
                ],
            })
        )

    document: dict[str, Any] = {
        "format": FORMAT,
        "project": {
            "id": project.id,
            "name": project.name,
            "address": addressing.project_address(project.name),
            "dimension": project.dimension or None,
            "genre": project.genre or None,
        },
        "systems": systems_out,
        "hud_layout": project.hud_layout or {},
        "state_schema": {
            key: {**entry, "address": addressing.state_address(key)}
            for key, entry in (project.state_schema or {}).items()
            if isinstance(entry, dict)
        },
        "yarn_declarations": _yarn_declarations(project.state_schema or {}),
        "abilities": [
            _addressed(project.id, "ability", {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "params": a.params or {},
                "unlock_requirements": a.unlock_requirements or [],
                "order": a.order,
            })
            for a in project.abilities.all()
        ],
        "characters": [
            _addressed(project.id, "character", {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "image_url": storage.view_url(c.image_key),
                "traits": _resolved_traits(c, project_trait_defs),
                "relationships": [
                    {
                        "to_character_id": r.to_character_id,
                        "to_name": r.to_character.name,
                        "relationship": r.relationship,
                    }
                    for r in c.relationships_out.select_related("to_character").all()
                ],
            })
            for c in project.characters.all()
        ],
        "entity_types": [
            _addressed(project.id, "entity", {
                "id": e.id,
                "name": e.name,
                "glyph": e.glyph,
                "category": e.category,
                "description": e.description,
                "behavior": e.behavior or {},
                "image_url": storage.view_url(e.image_key),
            })
            for e in entity_types
        ],
        "tile_legend": tile_legend,
        "levels": levels_out,
    }
    # One hash standing for the whole design, so "has anything changed at all?" is a single
    # comparison. Built from the per-object hashes rather than the document, so incidental
    # things that carry no hash (presigned image URLs, which are re-signed on every read)
    # can't make an unchanged design look modified.
    document["hash"] = addressing.rollup_hash(_object_hashes(document))
    return document


def _object_hashes(document: dict[str, Any]) -> list[str]:
    """Every per-object hash in the document, in no particular order (rollup_hash sorts)."""
    hashes = [entry["hash"] for entry in (document.get("systems") or {}).values()]
    for key in ("abilities", "characters", "entity_types"):
        hashes += [entry["hash"] for entry in document.get(key) or []]
    for level in document.get("levels") or []:
        hashes.append(level["hash"])
        hashes += [loc["hash"] for loc in level.get("locations") or []]
        hashes += [scene["hash"] for scene in level.get("scenes") or []]
    return hashes
