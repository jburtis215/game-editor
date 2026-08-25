"""MCP server for game-editor — the tool surface an AI game-creation agent talks to.

Every tool is a thin call onto the existing REST API (see `client.py`), so the model can
build a game the same way the UI does: create a project, set its dimension/genre and
systems, add levels, locations, scenes, characters, then write branching dialogue (or
paste/pull a whole scene as Yarn).

Two surfaces, and which one you want depends on why you're here:

* **Authoring** (`create_*` / `update_*`) — you are helping design the game.
* **Reading the design** (`get_blueprint`, `get_game_config`, `get_level_design`,
  `list_entity_types`) — you are *building* the game in an engine and need the plan. These
  serve slices of the `gameblueprint/0.1` export (contract: `docs/blueprint-schema.md`);
  start from the `/kickoff` prompt.

Run it over stdio:  ./.venv/bin/python -m mcp_server
"""
from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import client, conventions

mcp = FastMCP(
    "game-editor",
    instructions=(
        "Tools for designing a video game in game-editor and for building it from that design. "
        "The hierarchy is Project → Level → (Location, Scene) → Dialogue graph, with Characters "
        "and Abilities owned by the project. "
        "If you are BUILDING the game in an engine, start with get_game_config and "
        "get_level_design (or get_blueprint for the whole plan) — the design already answers "
        "questions like jump height, enemy behavior and level layout, so read it rather than "
        "inventing values. "
        "If you are AUTHORING the design, start with list_projects/create_project and work down. "
        "Dialogue is a graph, not a tree: create_dialogue makes a node (optionally attached to a "
        "parent) and link_dialogue attaches an existing node as another response, which is how "
        "branches converge. For bulk authoring, import_scene_yarn is usually faster than "
        "node-by-node."
    ),
)


def _slug(value: str) -> str:
    """Snake_case a label into a stable key. Mirrors `traitKey()` in the frontend."""
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_") or "state"


# --- Projects ---------------------------------------------------------------------------------
@mcp.tool()
async def list_projects() -> list[dict[str, Any]]:
    """List every game project with its settings, systems, and HUD layout."""
    return await client.get("/projects")


@mcp.tool()
async def get_project(project_id: int) -> dict[str, Any]:
    """Get one project: name, dimension, genre, systems config, HUD layout, state schema."""
    return await client.get(f"/projects/{project_id}")


@mcp.tool()
async def create_project(name: str = "New Project") -> dict[str, Any]:
    """Create a game project — the top-level container for levels, characters, and settings."""
    return await client.post("/projects", name=name)


@mcp.tool()
async def update_project(
    project_id: int,
    name: str | None = None,
    dimension: str | None = None,
    genre: str | None = None,
    systems: dict[str, Any] | None = None,
    hud_layout: dict[str, Any] | None = None,
    state_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a project's settings. Omitted fields are left unchanged.

    dimension: "2d" | "3d".
    genre: rpg | platformer | shooter | puzzle | social | card | strategy | racing |
        survival | horror | sandbox | fighting | rhythm.
    systems: the game-system architect answers, keyed by system id (health, stamina,
        movement, magic, inventory, combat, dialogue, …), each
        {"enabled": bool, "values": {question_id: answer}}. Read the current value first
        and merge — this call replaces the whole object.
    hud_layout: {systemId: {"x": int, "y": int}} for the Preview HUD.
    state_schema: the project's story-state variables, used by dialogue requirements/effects.
    """
    return await client.patch(
        f"/projects/{project_id}",
        name=name,
        dimension=dimension,
        genre=genre,
        systems=systems,
        hud_layout=hud_layout,
        state_schema=state_schema,
    )


# --- Abilities (the player's verb set) --------------------------------------------------------
@mcp.tool()
async def list_abilities(project_id: int | None = None) -> list[dict[str, Any]]:
    """List a project's abilities — everything the player can *do*.

    Each row carries `name`, `description` (behavior intent), `params` (the knobs that tune
    it) and `unlock_requirements` (empty = available from the start). Read this before
    building anything the player controls: the systems answers tune numbers, but this list
    is the verb set those numbers apply to.
    """
    return await client.get("/abilities", project_id=project_id)


@mcp.tool()
async def create_ability(
    project_id: int,
    name: str,
    description: str = "",
    params: dict[str, Any] | None = None,
    unlock_requirements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a player ability — one verb in the game's vocabulary ("Dash", "Double Jump").

    `description` is plain-language behavior intent, not code: "short burst forward, brief
    invulnerability". `params` is a free-form {key: number|string|bool} bag of the knobs
    that matter for this verb — {"cooldown": 1.5, "distance": 3, "uses": 2}; invent the
    keys the verb actually needs rather than forcing a fixed set.

    `unlock_requirements` gates when the player gets it, using the *same* bounded vocabulary
    as dialogue requirements (all must pass for the ability to be available):
        {"type": "state_equals", "state_key": "flag_met_mentor", "value": true}
        {"type": "stat_check", "state_key": "stat_strength", "op": "at_least|less_than|equals",
         "value": 3}
        {"type": "has_item", "state_key": "item_gauntlet"}
    Register each `state_key` with register_state_variable first. Leave the list empty for
    an ability the player starts with — that is the common case; gate only the abilities
    that are meant to be earned (ability gating is lock-and-key design's mechanic half, so
    plan the key before the verb it grants).
    """
    return await client.post(
        "/abilities",
        project_id=project_id,
        name=name,
        description=description,
        params=params or {},
        unlock_requirements=unlock_requirements or [],
    )


@mcp.tool()
async def update_ability(
    ability_id: int,
    name: str | None = None,
    description: str | None = None,
    params: dict[str, Any] | None = None,
    unlock_requirements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update an ability. Omitted fields are left unchanged; `params` and
    `unlock_requirements` each replace the whole value, so read the ability first and merge.

    Same vocabularies as create_ability.
    """
    return await client.patch(
        f"/abilities/{ability_id}",
        name=name,
        description=description,
        params=params,
        unlock_requirements=unlock_requirements,
    )


# --- Levels & locations -----------------------------------------------------------------------
@mcp.tool()
async def list_levels(project_id: int | None = None) -> list[dict[str, Any]]:
    """List levels, optionally only those in one project."""
    return await client.get("/levels", project_id=project_id)


@mcp.tool()
async def create_level(project_id: int, name: str = "New Level") -> dict[str, Any]:
    """Create a level in a project. It is appended after the project's current last level."""
    return await client.post("/levels", project_id=project_id, name=name)


@mcp.tool()
async def rename_level(level_id: int, name: str) -> dict[str, Any]:
    """Rename a level."""
    return await client.patch(f"/levels/{level_id}", name=name)


@mcp.tool()
async def list_level_cast(level_id: int) -> list[dict[str, Any]]:
    """The characters who appear in a level, deduced from who speaks its dialogue, each with
    the lines they speak. Use this to review a level's cast rather than guessing from names."""
    return await client.get(f"/levels/{level_id}/characters")


@mcp.tool()
async def list_locations(level_id: int | None = None) -> list[dict[str, Any]]:
    """List locations (places within a level), optionally filtered to one level.

    Each row carries the whole place: its detail fields (`kind`, `scale`, `mood`, `props`),
    the characters placed there, a reference `image_url`, and `connections` — its exits.
    Each connection is described relative to the row it appears on: `other_id`/`other_name`
    is the place at the far end, `direction` is "out" (authored here) or "in" (a
    bidirectional exit authored from the other side), and `requirements` is the lock on it.
    Read this before inventing a world's shape — the connections *are* the map.
    """
    return await client.get("/locations", level_id=level_id)


@mcp.tool()
async def create_location(
    level_id: int,
    name: str = "New Location",
    description: str = "",
    kind: str = "",
    scale: str = "",
    mood: str = "",
    props: list[str] | None = None,
) -> dict[str, Any]:
    """Create a location in a level — a place scenes can happen at and characters can stand in.

    Fill in the detail fields rather than leaving them for later; they are what a builder
    would otherwise have to invent.
    kind: "interior" | "exterior" | "" (unset).
    scale: "cramped" | "room" | "open" | "vast" | "" (unset).
    mood: free text — "smoky, candle-lit, too quiet".
    props: the things in the place — ["bar counter", "trapdoor behind the barrels"].
    """
    return await client.post(
        "/locations",
        level_id=level_id,
        name=name,
        description=description,
        kind=kind,
        scale=scale,
        mood=mood,
        props=props or [],
    )


@mcp.tool()
async def update_location(
    location_id: int,
    name: str | None = None,
    description: str | None = None,
    kind: str | None = None,
    scale: str | None = None,
    mood: str | None = None,
    props: list[str] | None = None,
) -> dict[str, Any]:
    """Update a location. Omitted fields are left unchanged; `props` replaces the whole list.

    Same field vocabulary as create_location (kind: interior|exterior; scale:
    cramped|room|open|vast) — this is how you flesh out a place that already exists.
    """
    return await client.patch(
        f"/locations/{location_id}",
        name=name,
        description=description,
        kind=kind,
        scale=scale,
        mood=mood,
        props=props,
    )


@mcp.tool()
async def connect_locations(
    from_location_id: int,
    to_location_id: int,
    label: str = "",
    bidirectional: bool = True,
    requirements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Connect two locations in the same level — a labeled exit in the world graph.

    `label` names the way through ("cellar door", "the rope bridge"). `bidirectional`
    (default) means it is walkable both ways and so appears on both locations; set it False
    for a one-way drop. `requirements` locks the passage, using the *same* bounded
    vocabulary as dialogue requirements (all must pass for the exit to be usable):
        {"type": "state_equals", "state_key": "flag_alarm_raised", "value": true}
        {"type": "stat_check", "state_key": "stat_strength", "op": "at_least|less_than|equals",
         "value": 3}
        {"type": "has_item", "state_key": "item_cellar_key"}
    Register each `state_key` with register_state_variable first. Gated connections are
    lock-and-key design: the world's shape is the progression, so plan the keys before the
    doors. Re-connecting the same ordered pair updates that connection instead of adding a
    second one. Returns the updated `from` location, including its connections.
    """
    return await client.post(
        f"/locations/{from_location_id}/connections",
        to_id=to_location_id,
        label=label,
        bidirectional=bidirectional,
        requirements=requirements or [],
    )


@mcp.tool()
async def place_character_at_location(location_id: int, character_id: int) -> dict[str, Any]:
    """Put a character at a location. The character must belong to the level's project."""
    return await client.post(f"/locations/{location_id}/characters", character_id=character_id)


@mcp.tool()
async def generate_location_art(location_id: int, prompt: str | None = None) -> dict[str, Any]:
    """Generate a reference image for a location with FLUX and attach it.

    Omit `prompt` to build one from the location's name, description, kind/scale and mood —
    so filling those in first gives a better image. Takes several seconds. Returns 503
    ("not configured") when the FAL/AWS credentials aren't set — that's an environment
    issue, not something to retry.
    """
    return await client.post(f"/locations/{location_id}/generate-image", prompt=prompt)


# --- Scenes -----------------------------------------------------------------------------------
@mcp.tool()
async def list_scenes(level_id: int | None = None) -> list[dict[str, Any]]:
    """List scenes, optionally only those in one level. A scene owns one dialogue graph."""
    scenes = await client.get("/scenes")
    if level_id is not None:
        scenes = [s for s in scenes if s.get("level_id") == level_id]
    return scenes


@mcp.tool()
async def create_scene(
    level_id: int, name: str = "New Scene", location_id: int | None = None
) -> dict[str, Any]:
    """Create a scene in a level, optionally set at a location. Dialogue hangs off scenes."""
    return await client.post("/scenes", level_id=level_id, name=name, location_id=location_id)


# --- Characters -------------------------------------------------------------------------------
@mcp.tool()
async def list_characters(project_id: int | None = None) -> list[dict[str, Any]]:
    """List characters, optionally only one project's. Characters are owned by a project."""
    return await client.get("/characters", project_id=project_id)


@mcp.tool()
async def get_character(character_id: int) -> dict[str, Any]:
    """Get a character: description, portrait URL, outgoing relationships, and raw traits.

    `traits` here is only what this character stores; use get_character_traits for the effective
    list with the project's defaults overlaid.
    """
    return await client.get(f"/characters/{character_id}")


@mcp.tool()
async def create_character(
    project_id: int, name: str = "New Character", description: str = ""
) -> dict[str, Any]:
    """Create a character in a project. The description also seeds AI portrait generation."""
    return await client.post(
        "/characters", project_id=project_id, name=name, description=description
    )


@mcp.tool()
async def update_character(
    character_id: int, name: str | None = None, description: str | None = None
) -> dict[str, Any]:
    """Update a character's name and/or description. Omitted fields are left unchanged."""
    return await client.patch(f"/characters/{character_id}", name=name, description=description)


@mcp.tool()
async def relate_characters(
    character_id: int, other_id: int, relationship: str = ""
) -> dict[str, Any]:
    """Add a directed, labeled relationship from one character to another (e.g. "mentor of").

    Unidirectional and shows only on `character_id`'s page — call again with the ids swapped
    for the reverse. Both characters must be in the same project. Re-calling the same pair
    updates the label.
    """
    return await client.post(
        f"/characters/{character_id}/relationships", other_id=other_id, relationship=relationship
    )


@mcp.tool()
async def generate_character_portrait(
    character_id: int, prompt: str | None = None
) -> dict[str, Any]:
    """Generate a portrait for a character with FLUX and attach it.

    Omit `prompt` to build one from the character's name + description. Takes several
    seconds. Returns 503 ("not configured") when the FAL/AWS credentials aren't set — that's
    an environment issue, not something to retry.
    """
    return await client.post(f"/characters/{character_id}/generate-image", prompt=prompt)


# --- Character traits -------------------------------------------------------------------------
# A trait is a named, typed slot on a character: number (Power = 75), text (Species = "Elf") or
# toggle (Can fly = true). The project holds a list of *default* trait definitions applied to every
# character; a character stores {"values": {key: value}, "own": [definition, ...]} — an override of
# a default, or a trait only it has. Defaults are overlaid live, so removing one from the project
# removes it everywhere. These tools compose GET + PATCH so the agent never hand-assembles the JSON.
TRAIT_TYPES = ("number", "text", "toggle")


def _trait_def(
    label: str,
    type: str,
    key: str | None = None,
    min: float = 0,
    max: float = 100,
    unit: str = "",
    default: Any = None,
) -> dict[str, Any]:
    if type not in TRAIT_TYPES:
        raise ValueError(f"type must be one of {', '.join(TRAIT_TYPES)}")
    definition: dict[str, Any] = {"key": key or _slug(label), "label": label, "type": type}
    if type == "number":
        definition.update(
            {"min": min, "max": max, "step": 1, "unit": unit, "default": min if default is None else default}
        )
    else:
        definition["default"] = (False if type == "toggle" else "") if default is None else default
    return definition


@mcp.tool()
async def list_project_character_traits(project_id: int) -> list[dict[str, Any]]:
    """The project's default character traits — the ones every character in it has."""
    project = await client.get(f"/projects/{project_id}")
    return list(project.get("character_traits") or [])


@mcp.tool()
async def add_project_character_trait(
    project_id: int,
    label: str,
    type: str = "number",
    min: float = 0,
    max: float = 100,
    unit: str = "",
    default: Any = None,
) -> dict[str, Any]:
    """Add a default trait to a project — every character in it gains this trait.

    `type` is number | text | toggle. `min`/`max`/`unit` apply to numbers only (a 0–100 stat is
    the usual shape). Omit `default` to start at `min` / "" / false. Re-adding an existing key
    replaces its definition. Returns the trait definition, including the generated `key` that
    set_character_trait takes.
    """
    definition = _trait_def(label, type, min=min, max=max, unit=unit, default=default)
    project = await client.get(f"/projects/{project_id}")
    traits = [t for t in (project.get("character_traits") or []) if t.get("key") != definition["key"]]
    traits.append(definition)
    await client.patch(f"/projects/{project_id}", character_traits=traits)
    return definition


@mcp.tool()
async def remove_project_character_trait(project_id: int, key: str) -> list[dict[str, Any]]:
    """Remove a default trait from a project. It disappears from every character immediately.

    Values characters had set for it are left behind harmlessly and ignored. Returns the
    remaining default traits.
    """
    project = await client.get(f"/projects/{project_id}")
    traits = [t for t in (project.get("character_traits") or []) if t.get("key") != key]
    await client.patch(f"/projects/{project_id}", character_traits=traits)
    return traits


@mcp.tool()
async def get_character_traits(character_id: int) -> list[dict[str, Any]]:
    """A character's effective traits: the project's defaults overlaid with this character's own.

    Each entry has the trait's definition plus `value` (the character's value, or the default it
    falls back to) and `source` — "project" for a project default, "own" for a trait only this
    character has.
    """
    character = await client.get(f"/characters/{character_id}")
    defaults: list[dict[str, Any]] = []
    if character.get("project_id"):
        project = await client.get(f"/projects/{character['project_id']}")
        defaults = list(project.get("character_traits") or [])
    stored = character.get("traits") or {}
    values = stored.get("values") or {}

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, defs in (("project", defaults), ("own", stored.get("own") or [])):
        for definition in defs:
            key = definition.get("key")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(
                {**definition, "value": values.get(key, definition.get("default")), "source": source}
            )
    return out


@mcp.tool()
async def set_character_trait(
    character_id: int,
    key: str,
    value: Any,
    label: str | None = None,
    type: str = "number",
    min: float = 0,
    max: float = 100,
) -> list[dict[str, Any]]:
    """Set one character's value for a trait, e.g. set Power to 75 on a character.

    `key` is a trait key from get_character_traits or add_project_character_trait. If it matches
    no existing trait, one is created *for this character only* — pass `label` (and `type` /
    `min` / `max` for a number) to define it; without a label the key is used as the label.
    To give the trait to every character instead, use add_project_character_trait.
    Returns the character's effective traits afterwards.
    """
    character = await client.get(f"/characters/{character_id}")
    stored = character.get("traits") or {}
    own = list(stored.get("own") or [])
    values = dict(stored.get("values") or {})

    known = {t.get("key") for t in own}
    if character.get("project_id"):
        project = await client.get(f"/projects/{character['project_id']}")
        known |= {t.get("key") for t in (project.get("character_traits") or [])}
    if key not in known:
        own.append(_trait_def(label or key, type, key=key, min=min, max=max, default=value))

    values[key] = value
    await client.patch(f"/characters/{character_id}", traits={"values": values, "own": own})
    return await get_character_traits(character_id)


@mcp.tool()
async def remove_character_trait(character_id: int, key: str) -> list[dict[str, Any]]:
    """Remove a trait from one character.

    A trait the character added itself is deleted outright. For a project default, this only
    clears the character's value so it falls back to the project's default — use
    remove_project_character_trait to drop it from everyone. Returns the effective traits after.
    """
    character = await client.get(f"/characters/{character_id}")
    stored = character.get("traits") or {}
    own = [t for t in (stored.get("own") or []) if t.get("key") != key]
    values = {k: v for k, v in (stored.get("values") or {}).items() if k != key}
    await client.patch(f"/characters/{character_id}", traits={"values": values, "own": own})
    return await get_character_traits(character_id)


# --- Story state ------------------------------------------------------------------------------
STATE_PREFIXES = {"flag": "flag", "remembered_choice": "choice", "item": "item", "stat": "stat"}


@mcp.tool()
async def register_state_variable(
    project_id: int, label: str, type: str = "flag", state_key: str | None = None
) -> dict[str, Any]:
    """Register a story-state variable on a project and return its `state_key`.

    Dialogue requirements/effects reference state by key; this is what gives that key a
    human-readable label in the editor (and in the Yarn export). Call it before using a new
    key. `type` is flag | remembered_choice | item | stat; the generated key follows the
    editor's convention (`flag_met_guard`, `item_cellar_key`, …). Re-registering an existing
    key just updates its label.
    """
    if type not in STATE_PREFIXES:
        raise ValueError(f"type must be one of {', '.join(STATE_PREFIXES)}")
    project = await client.get(f"/projects/{project_id}")
    schema: dict[str, Any] = dict(project.get("state_schema") or {})
    key = state_key or f"{STATE_PREFIXES[type]}_{_slug(label)}"
    schema[key] = {"id": key, "label": label, "type": type}
    await client.patch(f"/projects/{project_id}", state_schema=schema)
    return {"state_key": key, "label": label, "type": type}


@mcp.tool()
async def list_state_variables(project_id: int) -> list[dict[str, Any]]:
    """The project's story-state variables — the keys dialogue requirements/effects may use."""
    project = await client.get(f"/projects/{project_id}")
    return list((project.get("state_schema") or {}).values())


# --- Dialogue graph ---------------------------------------------------------------------------
@mcp.tool()
async def list_scene_dialogue(scene_id: int) -> list[dict[str, Any]]:
    """Every dialogue node in a scene, flat, each with its `parent_ids` — the whole graph in
    one call. Use this to see what exists before adding to it."""
    return await client.get(f"/scenes/{scene_id}/dialogues")


@mcp.tool()
async def get_dialogue(dialogue_id: int) -> dict[str, Any]:
    """One dialogue node with its speaker, its responses (outgoing edges), and the node(s)
    that link to it. No parents = a scene root."""
    return await client.get(f"/dialogues/{dialogue_id}")


@mcp.tool()
async def create_dialogue(
    scene_id: int,
    text: str = "",
    character_id: int | None = None,
    parent_id: int | None = None,
    requirements: list[dict[str, Any]] | None = None,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a dialogue node in a scene.

    Pass `parent_id` to attach it as a response of an existing node; omit it for a new root.
    `character_id` is the speaker (omit for narration).

    Every `state_key` should be one registered with register_state_variable, so the editor
    can label it. Requirements — gates; all must pass for this response to be offered:
        {"type": "state_equals", "state_key": "flag_met_guard", "value": true}
        {"type": "stat_check", "state_key": "stat_trust", "op": "at_least|less_than|equals",
         "value": 3}
        {"type": "has_item", "state_key": "item_lantern"}
    Effects — applied when the player picks this response:
        {"type": "set_flag", "state_key": "flag_met_guard", "label": "Met the guard",
         "value": true}
        {"type": "remember_choice", "state_key": "choice_spared_thief",
         "label": "Spared the thief"}
        {"type": "give_item", "state_key": "item_key", "label": "Cellar key"}
        {"type": "remove_item", "state_key": "item_key"}
        {"type": "change_stat", "state_key": "stat_trust", "label": "Trust", "amount": 1}

    The vocabulary is deliberately bounded to what Yarn's <<if>>/<<set>> can express — other
    shapes are stored but won't survive an export.
    """
    return await client.post(
        "/dialogues",
        scene_id=scene_id,
        parent_id=parent_id,
        character_id=character_id,
        text=text,
        requirements=requirements,
        effects=effects,
    )


@mcp.tool()
async def update_dialogue(
    dialogue_id: int,
    text: str | None = None,
    character_id: int | None = None,
    requirements: list[dict[str, Any]] | None = None,
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update a dialogue node. Omitted fields are left unchanged; `requirements`/`effects`
    replace the whole list when given (same vocabulary as create_dialogue)."""
    return await client.patch(
        f"/dialogues/{dialogue_id}",
        text=text,
        character_id=character_id,
        requirements=requirements,
        effects=effects,
    )


@mcp.tool()
async def link_dialogue(
    dialogue_id: int, target_id: int, option_label: str = ""
) -> dict[str, Any]:
    """Attach an existing node as an additional response of another node — no new node, just
    a new edge. This is how two branches converge back onto the same beat (or loop back).

    `option_label` is the player-facing choice text; blank falls back to the target's own text.
    """
    return await client.post(
        f"/dialogues/{dialogue_id}/link", target_id=target_id, option_label=option_label
    )


@mcp.tool()
async def import_scene_yarn(
    scene_id: int, text: str, parent_id: int | None = None
) -> dict[str, Any]:
    """Write a whole branching conversation into a scene from Yarn script text — the fastest
    way to author dialogue in bulk.

    Pass `parent_id` to hang the pasted content off an existing node instead of creating a
    new root. All-or-nothing: an unresolvable `<<jump>>` aborts the entire import. Returns
    how many nodes were created plus `warnings` for anything outside the supported subset
    (which is skipped, not guessed at) — always read the warnings back.

    Supported subset:

        title: NodeTitle
        ---
        Speaker: A line of dialogue.
        <<if $some_flag>>
        -> An option gated by that flag
            <<jump OtherNodeTitle>>
        -> An option with its own inline continuation
            Speaker: Said only if this option is picked.
        <<set $some_flag = true>>
        ===

    `<<jump X>>` may target a node later in the same paste or an existing node by title, so
    branches can converge onto content that is already there. `<<if>>`/`<<set>>` map onto the
    requirement/effect vocabulary; nested ifs, functions, and string variables are not
    supported.
    """
    return await client.post(f"/scenes/{scene_id}/import-yarn", text=text, parent_id=parent_id)


@mcp.tool()
async def export_scene_yarn(scene_id: int) -> dict[str, Any]:
    """Export a scene's whole dialogue graph as Yarn script text (plus a suggested filename).
    Good for reading a long conversation in one piece, or for round-tripping edits."""
    return await client.get(f"/scenes/{scene_id}/export-yarn")


# --- Reading the design (the build side: slices of the gameblueprint export) -------------------
# These wrap GET /projects/{id}/export — the canonical assembled document — rather than
# re-deriving anything, so every slice agrees with every other. The export is cheap and
# always current; it is refetched per call on purpose (no caching) so an agent never builds
# from a design the creator has since changed.


async def _blueprint(project_id: int) -> dict[str, Any]:
    return await client.get(f"/projects/{project_id}/export")


@mcp.tool()
async def get_engine_conventions(engine: str = "godot") -> dict[str, Any]:
    """How this design maps onto real files in a game engine. **Read before building.**

    Covers the unit conversion (one grid cell = one design unit = a fixed number of
    pixels, which is what makes the designer's jump height and gravity mean something),
    where each kind of object goes, which node type it becomes, how the tile glyphs
    translate, how to implement each entity behavior, what to do about dialogue, and the
    `game_editor_sync.json` you should keep alongside the build.

    These are prescribed for one reason: a later sync pass has to be able to find what you
    built and compare it to the design. Layout that changes session to session makes "not
    built" and "not found" the same answer. Within that, code structure and art are yours.

    Only Godot is covered so far.
    """
    try:
        return conventions.for_engine(engine)
    except KeyError as exc:
        raise client.ApiError(str(exc)) from exc


@mcp.tool()
async def get_manifest(project_id: int) -> dict[str, Any]:
    """**Read this first.** A map of the whole design — every object, one line each.

    Each entry has a stable `address` (`entity:goomba`, `system:movement`,
    `scene:the_handoff`) — the name to use for this thing everywhere, including in engine
    filenames and when reporting work back — plus a one-phrase `summary`, a content `hash`,
    and `depends_on`.

    Use it to decide what to pull in full: this index is small, the objects behind it are
    not. Then call get_level_design / get_game_config / list_entity_types for the parts you
    actually need.

    `depends_on` lists **facts of the design, not a build order**: an exit locked by
    `state:item_cellar_key` can't be opened before something grants that key (see that
    state entry's `granted_by`), an ability gated on a variable needs it declared, a scene
    needs the characters it casts. Sequence the work however you or the creator prefer —
    nothing here tells you which system to build first, on purpose.

    `hash` fingerprints each object's design. Record it alongside whatever you build from
    it; when the hash later differs, that object's design changed and the build is stale.
    `project.hash` covers the whole design, so one comparison answers "did anything change?"

    Addresses follow renames: if the creator renames "Walker" to "Goomba" the address
    becomes `entity:goomba`, `former_addresses` records the old one, and the engine-side
    artifact should be renamed to match. Key your own records on the object's numeric `id`,
    which never changes.
    """
    return await client.get(f"/projects/{project_id}/manifest")


@mcp.tool()
async def get_blueprint(project_id: int) -> dict[str, Any]:
    """The complete game design as one `gameblueprint/0.1` document — read this to build the game.

    Contains everything the design has decided: dimension/genre, per-system tuning with
    **derived feel numbers** (jump height in grid units, hang time, hits-to-die) and
    plain-language takeaways, the player's abilities, characters with resolved traits and
    relationships, the entity palette and tile legend, and every level's layout grid,
    entity coordinates, locations, connections and dialogue (as both a graph and ready
    Yarn script).

    **Treat these values as decisions, not suggestions** — if the design answers a question,
    implement that answer instead of picking a genre-typical default. If something genuinely
    isn't specified, say so rather than silently inventing it.

    Large for a big project: prefer get_game_config + get_level_design when you are working
    one level at a time.
    """
    return await _blueprint(project_id)


@mcp.tool()
async def get_game_config(project_id: int) -> dict[str, Any]:
    """The project-wide design *values*: settings, system tuning, abilities, story variables, HUD.

    The slice you need to scaffold a project and set up its systems. It deliberately does
    not enumerate characters, entities or levels — get_manifest indexes those far more
    cheaply, and list_entity_types / get_level_design pull them in full.

    `systems[id].derived` carries the numbers to implement (`jump_height_units`,
    `gravity_units_per_s2`, `hang_time_s`, `damage_per_hit`, `hits_to_die`) plus a
    `takeaway` string stating the intended feel in words. One "unit" is one cell of a level's
    layout grid, so a 3-unit jump clears a 3-cell wall.

    `yarn_declarations` is a ready `<<declare>>` block for every story variable — write it to
    a single Yarn file; the per-scene Yarn deliberately omits declares to avoid duplicate
    declarations across files.
    """
    bp = await _blueprint(project_id)
    return {
        "format": bp.get("format"),
        "project": bp.get("project"),
        "hash": bp.get("hash"),
        "systems": bp.get("systems"),
        "abilities": bp.get("abilities"),
        "state_schema": bp.get("state_schema"),
        "yarn_declarations": bp.get("yarn_declarations"),
        "hud_layout": bp.get("hud_layout"),
    }


@mcp.tool()
async def get_level_design(level_id: int) -> dict[str, Any]:
    """One level's full design: tile grid, entity placements, locations, and dialogue.

    `layout.rows` is the level as ASCII, one character per cell — `(0,0)` is the **top-left**
    cell, x grows rightward and y grows **downward**. `entities` is that same information
    already flattened to `{glyph, x, y, entity_type_id}` coordinates; use whichever is easier.
    Resolve glyphs through `tile_legend` (also returned here): `.` empty, `#` solid ground,
    `=` one-way platform (collidable from above only), `P` player start, `G` goal, and one
    glyph per entity type. `layout` is null when the designer hasn't drawn this level yet —
    ask rather than inventing a layout.

    `locations` is the narrative/spatial layer (places, their mood and props, and labeled —
    sometimes requirement-locked — connections between them); `scenes` carries each dialogue
    scene as a graph *and* as ready-to-compile Yarn. `on_complete.next_level_id` is where
    finishing this level leads (null = end of game).
    """
    level = await client.get(f"/levels/{level_id}")
    project_id = level.get("project_id")
    if not project_id:
        raise client.ApiError(
            f"Level {level_id} has no project, so its design can't be assembled."
        )
    bp = await _blueprint(project_id)
    for entry in bp.get("levels") or []:
        if entry.get("id") == level_id:
            return {
                **entry,
                "project_id": project_id,
                "tile_legend": bp.get("tile_legend"),
            }
    raise client.ApiError(f"Level {level_id} was not found in project {project_id}'s blueprint.")


@mcp.tool()
async def list_entity_types(project_id: int) -> dict[str, Any]:
    """The level palette — every placeable thing, plus the glyph legend for reading layouts.

    Each entity type has a one-character `glyph` (how it appears in `layout.rows`), a
    `category` (enemy / hazard / pickup / prop), a `description`, and a bounded `behavior`
    dict: `pattern` (static | walk | patrol | fly), `speed` in grid cells per second,
    `harmful_on_touch`, and `stompable` (Mario-style — jumping on top defeats it).
    Implement those semantics exactly; free-form nuance lives in `description`.

    `tile_legend` merges these glyphs with the five built-in tiles, so it is the complete
    key for any level's grid.
    """
    bp = await _blueprint(project_id)
    return {"entity_types": bp.get("entity_types"), "tile_legend": bp.get("tile_legend")}


# --- Reporting the build back (the write half of the loop) ------------------------------------
@mcp.tool()
async def report_built(
    project_id: int,
    address: str,
    engine_path: str = "",
    hash: str = "",
    status: str = "built",
    engine: str = "godot",
    note: str = "",
) -> dict[str, Any]:
    """Tell the platform you built something. **Call this as you finish each object.**

    The platform cannot see inside your engine project — there are no daemons and no
    plugins, by design — so this report is the only way it learns the thing exists. Work you
    don't report is indistinguishable from work never done.

    - `address` must come from get_manifest. An invented address is rejected, because a
      report nothing can match would look like unbuilt work forever.
    - `hash` is that object's `hash` at the time you built it. **Always pass it.** It is what
      lets the creator be told later that they changed the design after you built it —
      without you, or anyone, re-reading the code.
    - `engine_path` is where it lives (`res://entities/goomba.tscn`).
    - `status` is `in_progress`, `built` (default), or `verified` (you ran it and saw it work).

    Reporting the same object again updates the existing record, so it is safe to call after
    every revision. The reply tells you if the object is already stale, or if the creator has
    renamed it since — in which case rename the engine artifact and your sync manifest to
    match.
    """
    return await client.post(
        f"/projects/{project_id}/build-reports",
        address=address,
        engine_path=engine_path,
        hash=hash,
        status=status,
        engine=engine,
        note=note,
    )


@mcp.tool()
async def get_build_status(project_id: int, engine: str = "godot") -> dict[str, Any]:
    """What has been built so far, what has gone stale, and how much of the design is done.

    Read this at the **start of a session** to pick up where the last one left off, and
    whenever you want to know what changed since.

    Per object: `status` (not_built / in_progress / built / verified), `stale` (the design
    changed after it was built — re-read it and update the build), and `renamed` (the
    creator renamed it, so the engine artifact and your sync manifest entry are named wrong).

    `summary.percent_built` counts only objects that are built **and** current — a stale
    build is work still owed, not work finished. `orphaned_reports` lists things you built
    whose design object has since been deleted; those files are now unowned.
    """
    return await client.get(f"/projects/{project_id}/build-status", engine=engine)


# --- Resources (read-only context the agent can pull in) --------------------------------------
@mcp.resource("game-editor://projects", name="Projects", mime_type="application/json")
async def projects_resource() -> list[dict[str, Any]]:
    """Every game project in the editor."""
    return await client.get("/projects")


@mcp.resource(
    "game-editor://projects/{project_id}", name="Project overview", mime_type="application/json"
)
async def project_resource(project_id: str) -> dict[str, Any]:
    """A project with its levels, each level's scenes and locations, and the project's
    characters and abilities — the orienting snapshot to read before authoring anything.

    Built from the blueprint export so it can't drift from what the build tools serve; the
    per-level dialogue graphs are summarized rather than inlined to keep it readable (pull a
    full graph with get_level_design or the scene's Yarn resource)."""
    bp = await _blueprint(int(project_id))
    return {
        "project": bp.get("project"),
        "systems": {
            sys_id: state.get("derived") or {"enabled": state.get("enabled")}
            for sys_id, state in (bp.get("systems") or {}).items()
            if state.get("enabled")
        },
        "abilities": [
            {"id": a["id"], "name": a["name"], "description": a["description"]}
            for a in bp.get("abilities") or []
        ],
        "levels": [
            {
                "id": level.get("id"),
                "name": level.get("name"),
                "order": level.get("order"),
                "has_layout": bool(level.get("layout")),
                "locations": [
                    {"id": loc["id"], "name": loc["name"]} for loc in level.get("locations") or []
                ],
                "scenes": [
                    {
                        "id": scene["id"],
                        "name": scene["name"],
                        "is_intro": scene["is_intro"],
                        "node_count": len((scene.get("dialogue") or {}).get("nodes") or []),
                    }
                    for scene in level.get("scenes") or []
                ],
            }
            for level in bp.get("levels") or []
        ],
        "characters": [
            {"id": c["id"], "name": c["name"], "description": c["description"]}
            for c in bp.get("characters") or []
        ],
        "state_schema": bp.get("state_schema"),
    }


@mcp.resource(
    "game-editor://projects/{project_id}/blueprint",
    name="Game blueprint",
    mime_type="application/json",
)
async def blueprint_resource(project_id: str) -> dict[str, Any]:
    """The complete `gameblueprint/0.1` design document for a project — the whole plan an
    engine implementation should be built from. Same content as the get_blueprint tool."""
    return await _blueprint(int(project_id))


@mcp.resource(
    "game-editor://scenes/{scene_id}/yarn", name="Scene dialogue (Yarn)", mime_type="text/plain"
)
async def scene_yarn_resource(scene_id: str) -> str:
    """A scene's dialogue graph as Yarn script — the readable form of the whole conversation."""
    return (await client.get(f"/scenes/{scene_id}/export-yarn"))["text"]

@mcp.resource(
    "game-editor://conventions/{engine}",
    name="Engine conventions",
    mime_type="application/json",
)
async def conventions_resource(engine: str) -> dict[str, Any]:
    """How design objects map onto files in a given engine — the same content as the
    get_engine_conventions tool. Only `godot` is covered so far."""
    return conventions.for_engine(engine)


# --- Prompts ----------------------------------------------------------------------------------
@mcp.prompt(name="build-game", title="Build a game from a pitch")
def build_game_prompt(pitch: str, project_id: str = "") -> str:
    """Walk the agent through turning a one-line pitch into a populated project."""
    target = (
        f"Work inside existing project {project_id} (read game-editor://projects/{project_id} first)."
        if project_id
        else "Create a new project for it with create_project."
    )
    return f"""Build this game in game-editor: {pitch}

{target}

Then, in order:
1. Set the project's dimension and genre with update_project, and enable the game systems the
   pitch implies (read the current `systems` object first and merge your changes into it).
2. Create the characters the pitch needs (create_character), with descriptions concrete enough
   to draw, and wire their relationships with relate_characters.
3. Create at least one level, its locations, and a scene per beat.
4. Write each scene's dialogue. Prefer import_scene_yarn for a whole conversation at once, and
   read back its `warnings`. Register any story-state variables you need with
   register_state_variable, then use them in requirements/effects so choices matter, and
   link_dialogue where branches should converge.
5. Finish by exporting one scene with export_scene_yarn and summarizing what you built.

Ask before deleting or overwriting anything that already exists."""


@mcp.prompt(name="kickoff", title="Build a game from its blueprint")
def kickoff_prompt(project_id: str, target: str = "") -> str:
    """Brief the agent to build an already-designed game in an engine, from the blueprint."""
    engine = (target or "godot").strip().lower()
    known = engine in conventions.ENGINES
    engine_step = (
        f"Call get_engine_conventions('{engine}') — it says exactly where each kind of "
        "object goes, what node type it becomes, how the tile glyphs translate, and the "
        "pixels-per-cell constant that makes the design's numbers mean something."
        if known
        else (
            f"No conventions exist for '{target}' yet — only Godot. Agree a file layout and "
            "unit scale with the creator BEFORE building, and write it down, because a later "
            "sync pass has to be able to find what you built."
        )
    )
    return f"""Build project {project_id} in {target or "Godot"} from its design in game-editor.

The design is already made. Your job is to implement it faithfully, not to redesign it.

1. Read the map. Call get_manifest({project_id}) — one line per design object, each with the
   stable `address` to use for it everywhere. Then pull only what you need:
   get_game_config({project_id}) for project-wide values, get_level_design(level_id) for a
   level, list_entity_types({project_id}) for the glyph legend. get_blueprint({project_id})
   returns everything at once if the game is small.

   `depends_on` records what the design entails — a locked exit needs its key to exist
   first — not an order we are prescribing. Build in whatever order you and the creator
   choose; if the creator told you where to start, start there.

2. Read the conventions. {engine_step}

3. Honor the numbers. `systems[id].derived` holds the designer's tuned feel —
   `jump_height_units`, `gravity_units_per_s2`, `hang_time_s`, `damage_per_hit`,
   `hits_to_die` — each with a `takeaway` sentence saying what it should feel like. One
   "unit" is one cell of the level grid, so a 3-unit jump clears a 3-cell wall. Convert with
   the conventions' pixels-per-cell, once, and say which value you used.

4. Build each level from `layout.rows` exactly: `(0,0)` is top-left and y grows downward,
   which matches Godot 2D, so there is no vertical flip. Implement each entity's `behavior`
   dict (`pattern`, `speed`, `harmful_on_touch`, `stompable`) as written; anything it can't
   express is in `description`, so read that too.

5. Report each object as you finish it: call report_built({project_id}, address, engine_path,
   hash) with the object's `hash` from the manifest, and write the same three facts into
   `game_editor_sync.json`. The platform can't see your project, so unreported work is
   invisible to the creator — and the hash is what later tells them they changed a design
   you had already built.

   If you are resuming, start with get_build_status({project_id}) instead of rebuilding:
   it says what exists, what went `stale` (design changed since you built it) and what was
   `renamed` (rename the artifact to match).

6. **Never invent a value the design already answers.** If you need something the design
   doesn't specify, collect those gaps and list them at the end rather than filling them
   silently — the creator would rather decide than discover your default later.

Finish by summarizing what you built, the pixels-per-cell you used, and every gap you had to
leave open."""

if __name__ == "__main__":
    mcp.run()
