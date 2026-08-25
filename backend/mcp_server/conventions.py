"""Engine conventions — how a design object becomes a file in a specific engine.

This is not style advice. **Reconciliation depends on it.** The platform only learns what
was built because an agent reports it, and a later sync pass can only check the build by
looking where it expects things to be. If the agent invents a different layout each session,
"I couldn't find it" becomes indistinguishable from "it was never built", and the loop back
from engine to design quietly stops working.

So: prescribe exactly what makes an object locatable and its values comparable, and leave
everything else — code structure, art, feel-tuning within the design's numbers — to the
agent and the creator.

Godot is the only engine covered for now, deliberately. Naming a real target lets these say
`CharacterBody2D` and `res://entities/goomba.tscn` instead of hedged generalities, and
removing decisions is most of what makes an agent efficient rather than exploratory.
"""
from __future__ import annotations

from typing import Any

# One grid cell in pixels. Every "unit" in the design — jump height, run speed, gravity — is
# one cell, so this single constant converts all of them. 32 is the default because it puts
# a 100%-gravity design at 800 px/s², close to Godot's own 980 default, so a design tuned to
# feel normal in the platform also feels normal in Godot.
DEFAULT_PIXELS_PER_CELL = 32

GODOT: dict[str, Any] = {
    "engine": "godot",
    "godot_version": "4.4+",
    "why_this_matters": (
        "These conventions exist so the design and the build can be compared later. Put "
        "things where this says, name them what this says, and keep game_editor_sync.json "
        "current — that is what lets the platform tell you later that a design changed "
        "under something you already built."
    ),
    "units": {
        "rule": (
            "One cell of a level's layout grid = one design 'unit' = "
            f"{DEFAULT_PIXELS_PER_CELL} pixels. Convert every derived number with this one "
            "constant and state which value you used."
        ),
        "pixels_per_cell": DEFAULT_PIXELS_PER_CELL,
        "conversions": [
            "gravity_units_per_s2 * PPC = px/s^2   (25 -> 800; Godot's own default is 980)",
            "jump_velocity_units_per_s * PPC = px/s (12.25 -> 392), applied as NEGATIVE y",
            "run_speed_units_per_s * PPC = px/s     (8 -> 256)",
            "behavior.speed * PPC = px/s            (entity movement)",
        ],
        "axes": (
            "Godot 2D's +y points down, exactly like the layout grid's row index — grid "
            "(x, y) maps to world (x * PPC, y * PPC) with no vertical flip. Place an entity "
            "at the cell's centre: ((x + 0.5) * PPC, (y + 0.5) * PPC)."
        ),
    },
    "naming": {
        "rule": (
            "No case conversion. An address's slug is already snake_case, so it is the "
            "filename verbatim: entity:goomba -> res://entities/goomba.tscn. Node names, "
            "scene roots and class_names are PascalCase (Goomba). Address and filename must "
            "stay a pure identity mapping in both directions so either can be derived from "
            "the other without guessing."
        ),
        "renames": (
            "An address follows the creator's naming. If an object's address changed since "
            "you last built it (its former_addresses will show the old one), rename the "
            "engine artifact to match and update game_editor_sync.json. The object's numeric "
            "id never changes — match on id when an address no longer resolves."
        ),
    },
    "file_layout": {
        "entity:<slug>": "res://entities/<slug>.tscn",
        "level:<slug>": "res://levels/<slug>.tscn",
        "scene:<slug>": "res://dialogue/<slug>.yarn  (+ the runner reads the graph, see dialogue)",
        "state:*": "res://dialogue/variables.yarn — the whole yarn_declarations block, one file",
        "system:*": "res://config/game_config.gd — an autoload of constants, not a scene",
        "character:<slug>": (
            "res://characters/<slug>.tres — data + portrait. Only give a character a .tscn "
            "if they actually appear in the world."
        ),
        "ability:<slug>": "implemented on the player controller; recorded in game_config.gd",
        "_sync": "res://game_editor_sync.json — see sync_manifest",
    },
    "node_types": {
        "entity category enemy": "CharacterBody2D root, move_and_slide()",
        "entity category pickup": "Area2D root, body_entered -> collect",
        "entity category hazard": "Area2D root (static hazards need no body)",
        "entity category prop": "Node2D, or StaticBody2D if it collides",
        "level": (
            "Node2D root containing one TileMapLayer (Godot 4.3+ — not the deprecated "
            "TileMap), the instanced entity scenes, a PlayerSpawn Marker2D and a Goal Area2D"
        ),
    },
    "tiles": {
        ".": "empty — no tile",
        "#": "TileSet tile with full collision on all sides",
        "=": (
            "TileSet tile with ONE-WAY collision enabled, so the player passes up through it "
            "and lands on top. Not a separate scene — a tile property."
        ),
        "P": (
            "NOT a tile. A Marker2D named PlayerSpawn at that cell; instance the player there."
        ),
        "G": (
            "NOT a tile. An Area2D named Goal at that cell; entering it completes the level "
            "and advances to the level's on_complete.next_level_id."
        ),
        "any other glyph": (
            "an entity type — instance res://entities/<slug>.tscn at that cell. Resolve the "
            "glyph through the level's tile_legend."
        ),
        "note": (
            "The export's `entities` list already flattens the grid to coordinates and marks "
            "P/G with builtin:true, so you can place entities from it without re-parsing rows."
        ),
    },
    "behavior": {
        "rule": (
            "An entity's behavior dict is a bounded vocabulary — implement exactly these "
            "semantics. Nuance the dict can't express lives in `description`; read it."
        ),
        "pattern static": "does not move",
        "pattern walk": "moves in one direction at `speed`, does not turn at ledges",
        "pattern patrol": "moves at `speed`, turns at walls AND at ledges (check the floor ahead)",
        "pattern fly": "ignores gravity, moves at `speed`",
        "harmful_on_touch": "damages the player on contact, for health.damage_per_hit",
        "stompable": (
            "contact from above while the player is falling defeats this entity and bounces "
            "the player — the Mario rule. When false, contact from above still damages."
        ),
    },
    "dialogue": {
        "decision": (
            "Build a small GDScript dialogue player against each scene's `dialogue` graph. "
            "Do NOT take a Yarn Spinner dependency yet: the official GDScript port requires "
            "Godot 4.6+ and is alpha ('we do not recommend you use this to ship a game just "
            "yet'), and the C# port is an unsupported beta needing the .NET build."
        ),
        "also_write_the_yarn": (
            "Still write each scene's `yarn` text to res://dialogue/<slug>.yarn and the "
            "project's `yarn_declarations` to res://dialogue/variables.yarn. They are correct "
            "and portable, so moving to the Yarn addon on 4.6 later is a drop-in rather than "
            "a re-authoring."
        ),
        "runner": (
            "Start at the scene's root node(s) (`is_root`), show `text`, render outgoing "
            "edges as options using `option_label` (falling back to the target node's text). "
            "Filter an option out when its target's `requirements` don't pass; apply the "
            "chosen node's `effects` to a variables dictionary. The requirement/effect "
            "vocabulary is deliberately small, which is why this stays around 150 lines."
        ),
        "requirements": (
            "has_item -> vars[state_key] is true; stat_check -> compare vars[state_key] with "
            "`value` using `op` (at_least/less_than/equals); state_equals and "
            "remembered_choice -> vars[state_key] == `value`."
        ),
        "effects": (
            "give_item/remember_choice -> vars[state_key] = true; remove_item -> false; "
            "set_flag -> vars[state_key] = `value`; change_stat -> vars[state_key] += `amount`."
        ),
    },
    "sync_manifest": {
        "path": "res://game_editor_sync.json",
        "why": (
            "The engine-side half of the loop. It lives in the repo under version control, so "
            "changes to it show up in a diff, and it makes a later sync pass a lookup instead "
            "of a search. Write it as you build and keep it current."
        ),
        "shape": {
            "format": "game-editor-sync/1",
            "project_id": 4,
            "project_hash": "951afdfd",
            "pixels_per_cell": DEFAULT_PIXELS_PER_CELL,
            "objects": {
                "entity:goomba": {
                    "id": 4,
                    "path": "res://entities/goomba.tscn",
                    "hash": "b6f6b984",
                }
            },
        },
        "keying": (
            "Keyed by address because that is what a human reads in a diff — but every entry "
            "carries the numeric `id` as well, because addresses follow renames and ids do "
            "not. If an address stops resolving, find the entry by id and rename it."
        ),
        "hash": (
            "Record the object's `hash` at the moment you build it. That is what later makes "
            "'the design changed under this' detectable without anyone re-reading the code."
        ),
    },
    "out_of_scope": (
        "These conventions do not dictate code structure, art, or how you organise scripts "
        "within a scene — only what has to be predictable for the design and the build to be "
        "compared. Nothing here says which system to build first; that is the creator's call."
    ),
}

ENGINES = {"godot": GODOT}


def for_engine(engine: str) -> dict[str, Any]:
    key = (engine or "godot").strip().lower()
    if key not in ENGINES:
        supported = ", ".join(sorted(ENGINES))
        raise KeyError(f"No conventions for engine '{engine}'. Supported: {supported}.")
    return ENGINES[key]
