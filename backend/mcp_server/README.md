# game-editor MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the game-editor REST API as tools,
so an AI game-creation agent can build a game the same way the UI does.

It is a **client of the API**, not part of the Django app: every tool is an HTTP call to
`/api/...` (see `client.py`), so it can't bypass the validation the endpoints already do and it
works against a remote deployment just as well as localhost. The backend must be running.

## Run it

```bash
cd backend
./.venv/bin/python -m mcp_server          # stdio transport
```

Set `GAME_EDITOR_API_URL` if the API isn't at `http://127.0.0.1:8000/api`.

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

**Tools** — grouped the way the data model nests (Project → Level → Location/Scene → Dialogue,
with Characters owned by the project):

| Area | Tools |
| --- | --- |
| Projects | `list_projects`, `get_project`, `create_project`, `update_project` |
| Levels | `list_levels`, `create_level`, `rename_level`, `list_level_cast` |
| Locations | `list_locations`, `create_location`, `place_character_at_location` |
| Scenes | `list_scenes`, `create_scene` |
| Characters | `list_characters`, `get_character`, `create_character`, `update_character`, `relate_characters`, `generate_character_portrait` |
| Story state | `register_state_variable`, `list_state_variables` |
| Dialogue | `list_scene_dialogue`, `get_dialogue`, `create_dialogue`, `update_dialogue`, `link_dialogue`, `import_scene_yarn`, `export_scene_yarn` |

**Resources** (read-only context to pull in):

- `game-editor://projects` — every project
- `game-editor://projects/{project_id}` — a project with its levels, each level's scenes, and its
  characters; the orienting snapshot to read before authoring
- `game-editor://scenes/{scene_id}/yarn` — a scene's dialogue graph as Yarn script

**Prompt**: `build-game(pitch, project_id?)` — walks an agent from a one-line pitch through
settings → characters → levels/scenes → dialogue.

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
