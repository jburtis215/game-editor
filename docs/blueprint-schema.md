# gameblueprint/0.1 — export schema contract

The unified project export served by `GET /api/projects/{id}/export`. This is the document
the **MCP server** wraps (each read tool serves a slice of it) and the reference for anyone
consuming platform data. Built by `backend/api/services/blueprint.py` — change both together,
and bump `format` on any breaking change.

For the platformer demo, the MCP server can either call the export endpoint once and slice
it, or hit the underlying REST endpoints per tool (`/api/projects/{id}`, `/api/levels`,
`/api/entities?project_id=`, `/api/scenes/{id}/dialogues`) — the export is the same data
assembled canonically, so prefer wrapping the export.

## Top level

```jsonc
{
  "format": "gameblueprint/0.1",
  "project": { "id": 3, "name": "Sim Test", "dimension": "2d", "genre": "platformer" },
  "systems": { /* per-system config + derived feel numbers, see below */ },
  "hud_layout": { /* {systemId: {x, y}} — the designer's HUD mockup positions */ },
  "state_schema": { /* project-wide state variables used by dialogue requirements/effects */ },
  "yarn_declarations": "<<declare $item_key = false>>\n…",  // one block for the whole project
  "abilities": [ /* the player's verb set, with unlock gates */ ],
  "characters": [ /* speaking characters, portraits, relationships, resolved traits */ ],
  "entity_types": [ /* the level palette: enemies/hazards/pickups/props */ ],
  "tile_legend": { /* glyph -> meaning, built-ins + entities merged */ },
  "levels": [ /* ordered; layout grids, entity coords, locations, transitions, dialogue */ ]
}
```

## systems

Key = system id (`health`, `stamina`, `movement`, `magic`, `inventory`, `combat`,
`dialogue`). The question set is defined in `frontend/src/lib/gameSystems.ts`; only the
*answers* are stored/exported.

```jsonc
"movement": {
  "enabled": true,
  "values": { "scope": "all", "jumpHeight": 3, "gravity": 100, "runSpeed": 8 },
  "derived": {                       // present for health / movement / stamina
    "gravity_units_per_s2": 25.0,    // 1 "unit" = 1 grid cell of the level layout
    "jump_velocity_units_per_s": 12.25,
    "hang_time_s": 0.98,
    "run_speed_units_per_s": 8.0,
    "jump_height_units": 3.0,
    "takeaway": "Jumps 3 units high · ~1.0s of hang time"
  }
}
```

`derived` carries the same numbers that drive the platform's Systems-tab simulations
(`backend/api/services/derived.py`, ported from `frontend/src/lib/systemSimMath.ts`).
**Implementations should honor these numbers** — they are the designer's tuned "feel".
`takeaway` strings are plain-language design intent; surface them to the agent.

Health derived: `{ "damage_per_hit": 20.0, "hits_to_die": 8, "takeaway": "..." }` —
`hits_to_die` accounts for the regen mode (`values.regen`: `auto|pickup|rest|never`).

## yarn_declarations

A single ready-to-write block of Yarn `<<declare>>` lines covering every variable in
`state_schema` — booleans for `flag` / `remembered_choice` / `item`, `0` for `stat`, each
with the human label as a trailing comment.

Write it to **one** file (`variables.yarn` or equivalent) and drop the per-scene exports
beside it. This exists because `GET /api/scenes/{id}/export-yarn` deliberately omits
declares: scenes share state keys, and declaring the same variable in two `.yarn` files is
a Yarn Spinner compile error. Declaring once at project level is the resolution.

## abilities

The player's **verb set** — what the player can *do*, distinct from the systems
questionnaire (which tunes how those verbs feel).

```jsonc
{
  "id": 4, "name": "Double Jump", "description": "A second jump mid-air.",
  "params": { "cooldown": 0.5, "can_swing": true },   // invented per ability; free-form
  "unlock_requirements": [ { "type": "has_item", "state_key": "item_key" } ],
  "order": 0
}
```

`unlock_requirements` uses the same bounded requirement vocabulary as dialogue and
location connections; **empty means the player starts with the ability**. `params` keys are
designer-invented (`cooldown`, `distance`, `can_swing`) and stored verbatim — read them as
tuning hints, and let `description` settle anything ambiguous.

## entity_types

```jsonc
{
  "id": 1, "name": "Walker", "glyph": "e", "category": "enemy",   // enemy|hazard|pickup|prop
  "description": "A basic patrolling enemy. Turns around at edges and walls.",
  "behavior": {
    "pattern": "patrol",        // static | walk | patrol | fly
    "speed": 3,                 // units/sec (grid cells per second)
    "harmful_on_touch": true,
    "stompable": true           // Mario-style: jumping on top defeats it
  },
  "image_url": "https://…"      // presigned S3 URL, short-lived; "" if no image
}
```

`behavior` is a bounded vocabulary on purpose — implement exactly these semantics; free-form
nuance lives in `description`.

## levels + layout

Levels are ordered (`order`); completing one advances to `on_complete.next_level_id`
(`null` = game over/end). `intro_scene_id` names the dialogue scene to play at level start.

```jsonc
{
  "id": 2, "name": "Level 1", "order": 0,
  "layout": {
    "width": 20, "height": 6,
    "rows": [
      "....................",
      "..........o.........",
      ".....===............",
      "P........e.....^..G.",
      "####################",
      "####################"
    ]
  },
  "entities": [ /* coordinate list derived from rows, see below */ ],
  "intro_scene_id": 6,
  "on_complete": { "next_level_id": 3 },
  "locations": [ /* the level's places and how they connect, see below */ ],
  "scenes": [ /* dialogue scenes incl. the intro, see below */ ]
}
```

**Grid semantics.** One cell = one game unit (the same "unit" as movement's
`jump_height_units` — a 3-unit jump clears a 3-cell wall). `(x=0, y=0)` is the **top-left**
cell; `x` grows rightward, `y` grows **downward** (row index). `layout` is `null` when the
designer hasn't drawn the level yet.

**Built-in glyphs** (fixed meaning in every project):

| glyph | meaning |
|-------|---------|
| `.` | empty space |
| `#` | solid ground (collidable from all sides) |
| `=` | one-way platform (collidable from above only) |
| `P` | player start position |
| `G` | goal — touching it completes the level |

Every other glyph is an `entity_types[].glyph`. `tile_legend` merges both for convenience.

**`entities`** is the same information as the rows, pre-flattened into coordinates —
use whichever form is easier:

```jsonc
[
  { "glyph": "P", "builtin": true, "x": 0, "y": 3 },
  { "glyph": "e", "entity_type_id": 1, "x": 9, "y": 3 },
  { "glyph": "G", "builtin": true, "x": 18, "y": 3 }
]
```

(`"unknown": true` marks a glyph with no matching entity type — the API rejects these on
save, so it only appears in legacy/hand-seeded data. Treat as empty.)

## locations

A level's **places** — the narrative/spatial layer, orthogonal to the tile grid. A level can
have a layout and no locations (a pure action level), locations and no layout (a
conversation hub), or both.

```jsonc
{
  "id": 3, "name": "Overworld", "description": "…", "order": 0,
  "kind": "exterior",          // interior | exterior | ""
  "scale": "open",             // cramped | room | open | vast | ""
  "mood": "sunny, brisk",      // free text — the designer's felt sense of the place
  "props": ["pipes", "question blocks"],   // what's actually in it; don't invent extras
  "image_url": "https://… or ''",          // presigned reference art, short-lived
  "characters": [ { "id": 5, "name": "Mario" } ],   // who is present here
  "scene_ids": [8],                                  // dialogue scenes set here
  "connections": [ /* the exits, see below */ ]
}
```

**Connections are the world graph** — the room-and-exit structure, serialized *relative to
the location whose row they appear on*:

```jsonc
{
  "id": 2, "other_id": 4, "other_name": "Warp Pipe",
  "direction": "out",         // "out" = authored here; "in" = a two-way exit authored from the far end
  "label": "green pipe",
  "bidirectional": true,
  "requirements": [ { "type": "has_item", "state_key": "item_key" } ]   // the lock on this exit
}
```

A bidirectional connection appears on **both** locations it joins (once with
`direction: "out"`, once with `"in"`) and is walkable from either — the same `id` on both
rows. A one-way connection appears only on its source. `requirements` uses the bounded
requirement vocabulary, so a locked exit reads exactly like a gated dialogue choice; this
is lock-and-key design, and traversal order falls out of it.

## characters

```jsonc
{
  "id": 5, "name": "Elara", "description": "…", "image_url": "https://… or ''",
  "relationships": [ { "to_character_id": 7, "to_name": "Bram", "relationship": "mentor of" } ],
  "traits": [
    { "key": "power", "label": "Power", "type": "number", "min": 0, "max": 100,
      "default": 50, "value": 80, "source": "project" },
    { "key": "can_fly", "label": "Can fly", "type": "toggle",
      "default": false, "value": false, "source": "own" }
  ]
}
```

Relationships are directed edges (from this character to `to_character_id`).

`traits` is **already resolved** — the project's default traits overlaid with this
character's own, so `value` is the number/text/toggle to use and no further merging is
needed. `source` is `"project"` for a project-wide default (whether or not this character
overrode its value) or `"own"` for a trait only this character has. `type` is one of
`number` / `text` / `toggle`; a `number` carries `min` / `max` / `step` / `unit` when the
designer set them. Trait definitions are designer-invented, so treat `label` as the meaning.

## scenes + dialogue graphs

Each level's `scenes[]` carries its full dialogue graph — a **graph**, not a tree (nodes can
be reached from multiple parents; loops are legal). `is_intro` marks the level's intro scene.

```jsonc
{
  "id": 6, "name": "Opening", "order": 0, "is_intro": true,
  "location_id": 3,          // the location this scene plays at; null if unset
  "yarn": "title: opening_1\n---\nElara: …\n===\n",   // ready-to-compile Yarn for this scene
  "dialogue": {
    "nodes": [
      {
        "id": 41, "title": "opening_1",          // stable Yarn-friendly identifier
        "speaker": "Elara", "character_id": 5,
        "text": "The bridge is out. You'll have to jump.",
        "requirements": [],                       // gate: show only if all pass
        "effects": [],                            // apply when this node plays
        "is_root": true                           // entry point (no incoming edges)
      }
    ],
    "edges": [
      { "from": 41, "to": 42, "option_label": "Ask about the bridge", "order": 0 }
    ]
  }
}
```

- Play a scene by starting at its root node(s), showing outgoing edges as the player's
  choices; `option_label` falls back to the target node's `text` when blank.
- `requirements` / `effects` use the bounded vocabulary (types:
  `has_item | stat_check | state_equals | remembered_choice` and
  `give_item | remove_item | change_stat | set_flag | remember_choice`), each a dict with
  a `type` plus its parameters; `state_schema` declares the variables they reference.
- **`yarn`** is the same graph already compiled to Yarn script by the existing exporter —
  use it directly if you're targeting Yarn Spinner, and pair it with the project-level
  `yarn_declarations` block (this per-scene text deliberately carries no `<<declare>>`
  lines). Use `dialogue` instead if you're generating a non-Yarn dialogue runtime.

## MCP tool mapping

The read tools in `backend/mcp_server/server.py` are slices of this document — they all
wrap the export rather than re-deriving anything, so they can never disagree with each
other. Refetched per call (no caching), so an agent never builds from a stale design.

| tool | serves |
|------|--------|
| `get_blueprint(project_id)` | the whole document (small games) |
| `get_game_config(project_id)` | everything except level content, plus a `levels_summary` |
| `get_level_design(level_id)` | one `levels[]` entry — layout, entities, locations, scenes — plus `tile_legend` |
| `list_entity_types(project_id)` | `entity_types` + `tile_legend` |
| `get_character(id)` / `get_character_traits(id)` | one character; the second resolves project defaults |
| `export_scene_yarn(scene_id)` | one scene's Yarn (also inline on each scene as `yarn`) |

Resources: `game-editor://projects/{id}/blueprint` is this whole document;
`game-editor://projects/{id}` is a slimmed overview built from it. The `/kickoff` prompt
briefs an agent to build from the blueprint without inventing values it already answers.

All REST endpoints are unauthenticated localhost for the prototype (`http://localhost:8000`);
image URLs are short-lived presigned GETs — fetch them promptly, don't store them.
