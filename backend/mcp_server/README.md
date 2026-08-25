# game-editor MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the game-editor REST API as tools,
so an AI game-creation agent can build a game the same way the UI does.

It is a **client of the API**, not part of the Django app: every tool is an HTTP call to
`/api/...` (see `client.py`), so it can't bypass the validation the endpoints already do and it
works against a remote deployment just as well as localhost. The backend must be running.

## Run it

```bash
cd backend
./.venv/bin/pip install -r requirements.txt   # needs `mcp` (pinned <2) and `httpx`
./.venv/bin/python -m mcp_server              # stdio transport
```

Set `GAME_EDITOR_API_URL` if the API isn't at `http://127.0.0.1:8000/api`.

> `mcp` is pinned to **v1** in `requirements.txt`: this server is written against `FastMCP`,
> which v2 renamed to `MCPServer`. Migrating is a deliberate separate change.

## Wire it into a client

You normally register this from **the game project's directory** (a Godot project, say), not
from this repo — that is where the agent doing the building runs.

> **`PYTHONPATH` is required.** `python -m mcp_server` only resolves when `backend/` is on
> `sys.path`, so running it from any other directory fails with `No module named mcp_server`.
> Either set `PYTHONPATH` as below, or set the process's working directory to `backend/`.

Claude Code — run this in the game project's directory:

```bash
claude mcp add game-editor \
  -e PYTHONPATH=/absolute/path/to/backend \
  -- /absolute/path/to/backend/.venv/bin/python -m mcp_server
```

Add `-s project` to write it to `.mcp.json` in that project instead of your local config, so
it travels with the repo. Then `/mcp` inside Claude Code should show `game-editor` connected,
and the server's prompts appear as `/mcp__game-editor__kickoff`.

Claude Desktop (`claude_desktop_config.json`) or any other MCP client — `cwd` does the same
job as `PYTHONPATH` here:

```json
{
  "mcpServers": {
    "game-editor": {
      "command": "/absolute/path/to/backend/.venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/backend",
      "env": { "GAME_EDITOR_API_URL": "http://127.0.0.1:8000/api" }
    }
  }
}
```

**The Django API must be running** (`npm run dev:api`) — this server is an HTTP client of it
and has no database access of its own.

## What it exposes

There are **two surfaces**, and which one an agent wants depends on why it's here.

### Reading the design (the build side)

For an agent implementing the game in an engine. Every one of these is a slice of the
`gameblueprint/0.1` export (`GET /api/projects/{id}/export`, contract in
`docs/blueprint-schema.md`) — they wrap it rather than re-deriving anything, so no two
slices can disagree, and each refetches so the agent never builds from a stale design.

| Tool | Serves |
| --- | --- |
| `get_manifest(project_id)` | **the intended first read** — one line per design object: stable address, one-phrase summary, content hash, and the dependencies the design entails |
| `get_blueprint(project_id)` | the entire design document |
| `get_game_config(project_id)` | project-wide *values*: settings, system tuning + derived feel numbers, abilities, story variables, HUD |
| `get_level_design(level_id)` | one level: tile grid, entity coordinates, locations + connections, scenes (graph *and* Yarn), and the tile legend |
| `list_entity_types(project_id)` | the level palette + the glyph legend |
| `get_engine_conventions(engine)` | how design objects become real files — layout, node types, tile semantics, units, sync manifest. Godot only so far |

Start an engine build from the **`kickoff`** prompt, which briefs the agent to honor the
design's numbers instead of substituting genre defaults.

The manifest is a **map, not a route**. Its `depends_on` edges are entailments of what the
creator authored (a locked exit needs its key; a scene needs its cast), never a build order
this platform invented — sequencing is the agent's or the creator's call. See
`api/services/manifest.py`.

Every object carries a stable **address** (`entity:goomba`) to name it by and a content
**hash** to version it. Addresses follow renames — the numeric `id` is the identity that
doesn't — so an agent should key its own records on `id`, name engine artifacts after the
address, and store the hash to detect later that a design changed under a finished build.

### Reporting the build back

The platform can't see inside an engine project — no daemons, no plugins, agent-mediated
only — so these are the only way it learns anything was built.

| Tool | Does |
| --- | --- |
| `report_built(project_id, address, engine_path, hash, status?)` | records one built object against the design `hash` it was built from |
| `get_build_status(project_id)` | what's built, what's `stale` (design changed since), what's `renamed`, and `percent_built` |

The `hash` is the point. Once an object is reported as built against one, the platform can
tell **on its own** that the creator has since changed that object — no engine access, no
reconcile pass. `percent_built` counts only objects that are built *and* current, so a
stale build reads as work still owed. Staleness and renames are derived at read time, never
stored: a stored flag would need invalidating every time the design changed, which is the
bug it exists to catch.

### Authoring the design

Grouped the way the data model nests (Project → Level → Location/Scene → Dialogue, with
Characters and Abilities owned by the project):

| Area | Tools |
| --- | --- |
| Projects | `list_projects`, `get_project`, `create_project`, `update_project` |
| Abilities | `list_abilities`, `create_ability`, `update_ability` |
| Levels | `list_levels`, `create_level`, `rename_level`, `set_level_layout`, `list_level_cast` |
| Entity palette | `create_entity_type`, `update_entity_type`, `seed_entity_palette` |
| Locations | `list_locations`, `create_location`, `update_location`, `connect_locations`, `place_character_at_location`, `generate_location_art` |
| Scenes | `list_scenes`, `create_scene` |
| Characters | `list_characters`, `get_character`, `create_character`, `update_character`, `relate_characters`, `generate_character_portrait` |
| Character traits | `list_project_character_traits`, `add_project_character_trait`, `remove_project_character_trait`, `get_character_traits`, `set_character_trait`, `remove_character_trait` |
| Story state | `register_state_variable`, `list_state_variables` |
| Dialogue | `list_scene_dialogue`, `get_dialogue`, `create_dialogue`, `update_dialogue`, `link_dialogue`, `import_scene_yarn`, `export_scene_yarn` |

**Resources** (read-only context to pull in):

- `game-editor://projects` — every project
- `game-editor://projects/{project_id}` — a project with its levels, each level's scenes and
  locations, its characters and abilities; the orienting snapshot to read before authoring.
  Built from the blueprint, with dialogue graphs summarized rather than inlined
- `game-editor://projects/{project_id}/blueprint` — the full `gameblueprint/0.1` document
- `game-editor://scenes/{scene_id}/yarn` — a scene's dialogue graph as Yarn script
- `game-editor://conventions/{engine}` — the engine conventions above

**Prompts**:

- `kickoff(project_id, target?)` — build an already-designed game in an engine from its
  blueprint. Points at the manifest and the engine conventions, insists on the design's
  numbers, requires the build be recorded in `game_editor_sync.json`, and carries the rule
  that matters most: never invent a value the design already answers. When `target` is an
  engine with no conventions yet, it says so and tells the agent to agree a layout with the
  creator first rather than improvising one.
- `build-game(pitch, project_id?)` — the other direction: walk an agent from a one-line pitch
  through settings → characters → levels/scenes → dialogue.

## Notes for whoever extends this

- Tool docstrings are the agent-facing documentation — the requirement/effect vocabulary and the
  supported Yarn subset are spelled out there on purpose. Keep them in sync with
  `frontend/src/api/client.ts` (`DialogueRequirement`/`DialogueEffect`) and
  `api/services/yarn_import.py`.
- `register_state_variable` is the one tool that composes rather than proxies (GET + PATCH of
  `project.state_schema`), because an agent writing a `state_key` the editor has never seen would
  otherwise leave unlabeled variables in the UI.
- Everything is read/create/update. No delete tools are exposed (only locations and relationships
  have DELETE endpoints anyway) — add them deliberately if an agent should be able to destroy work.
- The conventions tell a builder to **greybox** — flat coloured rectangles, one cell each,
  fixed colours per category — rather than stall on missing art. Entity `image_url` is
  usually empty and is a short-lived presigned URL when it isn't, so it is never something a
  build should depend on fetching.
- `conventions.py` is prescriptive *only* where reconciliation needs it — file location,
  naming, units, and the sync manifest. If the agent lays a project out differently each
  session, a later sync pass can't tell "not built" from "not found", and the loop back from
  engine to design stops working. Code structure and art are deliberately left alone.
- **Dialogue is intentionally not on Yarn Spinner yet.** The official GDScript port needs
  Godot 4.6+ and is alpha ("we do not recommend you use this to ship a game just yet"); the
  C# port is an unsupported beta needing the .NET build. The conventions have the agent build
  a small GDScript player against the `dialogue` graph while still writing the `.yarn` files,
  so adopting the addon later is a drop-in.
- The read tools deliberately **wrap the export** instead of composing REST calls. One assembly
  path means the schema contract is enforced in one place (`api/services/blueprint.py`), and a
  new field reaches every tool at once. The cost is that a slice fetches the whole document;
  revisit if projects get big enough for that to matter.
