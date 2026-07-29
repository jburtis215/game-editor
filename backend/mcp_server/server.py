"""MCP server for game-editor — the tool surface an AI game-creation agent talks to.

Every tool is a thin call onto the existing REST API (see `client.py`), so the model can
build a game the same way the UI does: create a project, set its dimension/genre and
systems, add levels, locations, scenes, characters, then write branching dialogue (or
paste/pull a whole scene as Yarn).

Run it over stdio:  ./.venv/bin/python -m mcp_server
"""
from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import client

mcp = FastMCP(
    "game-editor",
    instructions=(
        "Tools for authoring a video game in game-editor. The hierarchy is "
        "Project → Level → (Location, Scene) → Dialogue graph, with Characters owned by the "
        "project. Start with list_projects/create_project, then work down. Dialogue is a "
        "graph, not a tree: create_dialogue makes a node (optionally attached to a parent) and "
        "link_dialogue attaches an existing node as another response, which is how branches "
        "converge. For bulk authoring, import_scene_yarn is usually faster than node-by-node."
    ),
)

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
    """List locations (places within a level), optionally filtered to one level. Each includes
    the characters placed there."""
    return await client.get("/locations", level_id=level_id)


@mcp.tool()
async def create_location(
    level_id: int, name: str = "New Location", description: str = ""
) -> dict[str, Any]:
    """Create a location in a level — a place scenes can happen at and characters can stand in."""
    return await client.post(
        "/locations", level_id=level_id, name=name, description=description
    )


@mcp.tool()
async def place_character_at_location(location_id: int, character_id: int) -> dict[str, Any]:
    """Put a character at a location. The character must belong to the level's project."""
    return await client.post(f"/locations/{location_id}/characters", character_id=character_id)


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
    """Get a character: description, portrait URL, and outgoing relationships."""
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


# --- Story state ------------------------------------------------------------------------------
STATE_PREFIXES = {"flag": "flag", "remembered_choice": "choice", "item": "item", "stat": "stat"}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_") or "state"


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


# --- Resources (read-only context the agent can pull in) --------------------------------------
@mcp.resource("game-editor://projects", name="Projects", mime_type="application/json")
async def projects_resource() -> list[dict[str, Any]]:
    """Every game project in the editor."""
    return await client.get("/projects")


@mcp.resource(
    "game-editor://projects/{project_id}", name="Project overview", mime_type="application/json"
)
async def project_resource(project_id: str) -> dict[str, Any]:
    """A project with its levels, each level's scenes, and the project's characters — the
    orienting snapshot to read before authoring anything."""
    project = await client.get(f"/projects/{project_id}")
    levels = await client.get("/levels", project_id=project_id)
    scenes = await client.get("/scenes")
    characters = await client.get("/characters", project_id=project_id)
    by_level: dict[int, list[dict[str, Any]]] = {}
    for scene in scenes:
        by_level.setdefault(scene["level_id"], []).append(scene)
    return {
        "project": project,
        "levels": [{**level, "scenes": by_level.get(level["id"], [])} for level in levels],
        "characters": characters,
    }


@mcp.resource(
    "game-editor://scenes/{scene_id}/yarn", name="Scene dialogue (Yarn)", mime_type="text/plain"
)
async def scene_yarn_resource(scene_id: str) -> str:
    """A scene's dialogue graph as Yarn script — the readable form of the whole conversation."""
    return (await client.get(f"/scenes/{scene_id}/export-yarn"))["text"]


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


if __name__ == "__main__":
    mcp.run()
