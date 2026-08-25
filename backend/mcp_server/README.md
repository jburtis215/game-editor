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

Claude Code (from the repo root):

```bash
claude mcp add game-editor -- /absolute/path/to/backend/.venv/bin/python -m mcp_server
```

Claude Desktop (`claude_desktop_config.json`) or any other MCP client:

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

### Authoring the design

Grouped the way the data model nests (Project → Level → Location/Scene → Dialogue, with
Characters and Abilities owned by the project):

| Area | Tools |
| --- | --- |
| Projects | `list_projects`, `get_project`, `create_project`, `update_project` |
| Abilities | `list_abilities`, `create_ability`, `update_ability` |
| Levels | `list_levels`, `create_level`, `rename_level`, `list_level_cast` |
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

**Prompts**:

- `kickoff(project_id, target?)` — build an already-designed game in an engine from its
  blueprint. Names the unit convention, the glyph semantics, the Yarn declare split, and the
  rule that matters most: never invent a value the design already answers.
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
- The read tools deliberately **wrap the export** instead of composing REST calls. One assembly
  path means the schema contract is enforced in one place (`api/services/blueprint.py`), and a
  new field reaches every tool at once. The cost is that a slice fetches the whole document;
  revisit if projects get big enough for that to matter.
