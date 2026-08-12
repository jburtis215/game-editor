# CLAUDE.md

Project context for Claude Code. Read this before making changes.

## What this is

`game-editor` is an early-stage **Figma-like design platform** for building games. The top level is
a **Project** (a game), which has tabs: **Settings** (2D/3D + genre), **Systems** (a game-system
architect — health, magic, inventory, … with per-system questions, producing an "ai-game-maker"
blueprint), **Preview** (a draggable retro HUD layout), and **Levels** (each Level has a
**branching dialogue editor**). A standalone **shape editor** (SVG outlines) also exists (route
kept, no nav). It is intentionally minimal — favor small, readable additions over large
abstractions until the feature set grows.

The Systems/Settings/Preview tabs were consolidated from the `prototypes/lovable-game-systems-pages/`
Lovable prototype (a different stack — TanStack/Tailwind/shadcn); their data + logic were **ported**
into our Vite/plain-CSS/typed-Ninja conventions (`src/lib/gameSystems.ts`). The prototype dir is
kept for reference.

## Architecture

Polyglot monorepo. The frontend is an npm workspace; the backend is a Python/Django project.

```
frontend/   React 19 + TypeScript 6 + Vite 8 (npm). SVG-based shape rendering.
backend/    Django 5.2 + Django Ninja (Python 3.11, venv). Server for heavier tasks.
            Postgres 14 is the database (local: db `game_editor`, role `game_editor`).
```

Toolchain: Node 24 (LTS), npm 11 (frontend); Python 3.11 + `backend/.venv` (backend).
`frontend/src/vite-env.d.ts` (`/// <reference types="vite/client" />`) provides the ambient
module declarations for CSS/asset imports — keep it.

### Frontend (`frontend/`)
- Entry: `src/main.tsx` wraps `<App>` in `<BrowserRouter>` (react-router). `src/App.tsx` is the
  shell: top nav + `<Routes>`. **Projects are the top level**: `/` = `ProjectsPage` (list with
  add + inline rename). Clicking a project opens `/projects/:projectId` = `ProjectHomePage`, a
  **layout route with a tab bar** (Settings · Systems · Levels · Characters · Preview) that
  renders an `<Outlet/>`; the index redirects to `settings`. Tab child routes:
  `settings` = `ProjectSettingsPage` (dimension + genre + default character traits),
  `systems` = `ProjectSystemsPage`
  (game-system architect + blueprint), `preview` = `ProjectPreviewPage` (draggable retro HUD),
  `levels` = `LevelsPage` (project-scoped list), `characters` = `CharactersPage` (project-scoped
  list + create). Drilling in is a **full page outside the tab layout**:
  `/projects/:projectId/levels/:levelId` = `LevelHomePage` (hub with Dialogue + Characters tiles),
  `/projects/:projectId/levels/:levelId/dialogue` = `DialogueEditorPage`,
  `/projects/:projectId/levels/:levelId/characters` = `LevelCharactersPage` (the level's cast,
  **deduced from dialogue speakers**, each with their lines + an Actions TODO stub), and
  `/projects/:projectId/characters/:characterId` = `CharacterDetailPage` (edit name/description,
  manage relationships, edit traits). `/shapes` = `ShapeEditorPage`
  (route kept; no nav). **Characters are per-project** — there is no global `/characters` route or
  nav item.
- **Characters** (`pages/CharactersPage.tsx` + `CharacterDetailPage.tsx`): the list is a card grid
  (`Characters.css`) scoped via `GET /api/characters?project_id=`; "＋ New character" POSTs then
  routes to the detail page. Detail edits persist with `PATCH /api/characters/{id}`.
  **Relationships are directed (unidirectional)**: adding one (`POST …/relationships`) creates an
  edge from this character to the target and shows only on this character's page; the reverse is a
  separate edge. Remove via `DELETE …/relationships/{id}`.
- **Character traits** (`src/lib/characterTraits.ts` + `components/traits/`): a trait is a named,
  typed slot — `number` (Power = 75), `text` (Species = "Elf") or `toggle` (Can fly ✓). The
  **Settings tab** picks the project's *default* traits (`Project.character_traits`), which are
  **overlaid live** onto every character at render time — removing one there removes it from every
  character instantly, no backfill. `CharacterDetailPage` shows the resolved list
  (`resolveTraits()`): project defaults badged `default` with a ↺ that drops the character's
  override, plus traits only that character has (added via `TraitPicker`, removable). Unlike
  `gameSystems.ts` (definitions in code, answers in JSON), a trait's **full definition is
  persisted** — traits can be custom, so no code catalog could describe them; `TRAIT_CATALOG`
  (~55 traits over 7 categories) is only a picker source, and editing it never invalidates saved
  data. `normalizeTraitDefs()`/`normalizeCharacterTraits()` coerce the loose JSON, so **the backend
  does no trait validation**. Both pages debounce saves (~400ms) because the number control is a
  slider; `CharacterDetailPage` is outside the tab layout so it has no `useProject()` — it fetches
  `GET /api/projects/{id}` itself for the defaults.
- `ProjectHomePage` fetches the project and passes `{ project, patchProject }` to its tabs via
  **`useOutletContext`** (`useProject()` helper). `patchProject(partial)` does an optimistic
  `PATCH /api/projects/{id}`; the Systems/Preview tabs keep a local working copy and **debounce**
  saves (~400ms) so dragging/sliding doesn't flood the API.
- **Game-system definitions** live in `src/lib/gameSystems.ts` (ported from the Lovable
  prototype): `DIMENSIONS`, `GENRES`, `SYSTEMS` (each with `single|multi|slider` questions),
  `genreDefaults()`, `buildManifest()`, plus `normalizeSystems()`/`normalizeHudLayout()` that
  coerce the project's JSON fields into well-formed typed state. **This module is the source of
  truth for the question set** — the DB only stores the *answers*. Edit questions here, not in the
  DB.
- **Theming**: the palette is CSS variables under `[data-theme='neon'|'aqua'|'light'|'studio']` in
  `App.css` (`studio` is the clean teal/light look ported from the prototype); `App.tsx` sets
  `document.documentElement.dataset.theme` and persists the choice via `PATCH /api/user`. Accent
  shades use `color-mix(... var(--orange)/var(--green) ...)` so all themes stay consistent —
  **don't hardcode accent `rgba()`** in component CSS. Adding a theme = add a `[data-theme=...]`
  block + append the name to `User.THEME_CHOICES` (backend) and `THEMES`/`THEME_LABELS` (frontend).
- **Typed API client**: `src/api/client.ts` is an `openapi-fetch` client typed by
  `src/api/schema.d.ts`, which is **generated** from the backend's OpenAPI spec via
  `npm run gen:api` (backend must be running). Don't hand-edit `schema.d.ts`; regenerate it.
  Re-export backend schemas as TS types from `client.ts` (e.g. `Project`, `DialogueDetail`, `Scene`).
- **Shape editor** (`pages/ShapeEditorPage.tsx`): holds `shapes`/`tool` in `useState`.
  `src/types.ts` defines the `Shape` model (reuse it). `components/{Toolbar,Canvas,Shape}.tsx`
  render the SVG canvas (create via click-drag with a shape tool, move via the select tool).
- **Dialogue editor** (`pages/DialogueEditorPage.tsx`): reached via a project's Levels tab → a
  level; reads `projectId`/`levelId` from the route and filters `/api/scenes` to that level.
  **Scoped to a scene**: owns `sceneId` + `currentId`; selecting a scene loads its root via
  `GET /api/dialogues?scene_id=`, then `GET /api/dialogues/{id}` for the focused node. A dialogue
  is a node in a **graph**, not a tree — it can be reached from more than one place (see the
  backend model below), so `detail.parents` is a list: "Back to parent" is a plain button when
  there's exactly one, and a picker when a node is reached from several places. Components in
  `components/dialogue/`: `ScenesSidebar` (left, controlled — switches the active scene),
  `CharactersSidebar` (right), `DialogueBlob` (current node + Edit), `ResponseWheel` (horizontal
  child cards; shows each edge's `option_label`, falling back to the target's own text; click →
  `currentId`), `DialogueForm` (shared add/edit; its speaker `<select>` has a **"＋ New"** action
  that creates a character inline via `DialogueEditorPage.createCharacter` → `POST /api/characters`
  and selects it). Add/Edit call `POST`/`PATCH /api/dialogues` (new nodes inherit the current
  `sceneId`; `parent_id` attaches the new node as a response of another).
  A **Focus ⇄ Tree toggle** (`viewMode`) switches the stage between the one-node focused view above
  and **`DialogueTree`** — a zoomable/pannable **React Flow** (`@xyflow/react`) canvas of the whole
  scene. Tree mode fetches the flat node list via `GET /api/scenes/{id}/dialogues` (into `treeNodes`,
  refetched after add/edit; each node's `parent_ids` is a list), hand-lays-out a tidy top-down tree
  (`layoutTree`, no layout lib — a node with multiple parents is positioned under its first/primary
  parent for layout, but every incoming edge still renders as a line, so reconvergence is visible),
  renders custom node cards (avatar + speaker + text) with `<Controls>`/`<Background>`; on
  node-click it sets `currentId` (so the reused `DialogueBlob` below acts as the edit inspector)
  and `setCenter`s to zoom in on that node. **Import/Export Yarn** panels (buttons next to the
  Focus/Tree toggle) round-trip a scene's graph to/from Yarn script text — see the backend bullet
  below for exactly what's supported.

### Backend (`backend/`) — Django + Django Ninja
- `config/` — Django project: `settings.py` (env-driven via `.env`, see `.env.example`),
  `urls.py` (mounts admin at `/admin/` and the Ninja API at `/api/`), `wsgi.py`/`asgi.py`.
- `api/` — the Django Ninja app. `api/api.py` defines the `NinjaAPI` instance and endpoints.
  - `POST /api/auth` — placeholder that always returns **HTTP 400**. Deliberate stub, not called
    by the frontend. Don't wire it up or change its status without a reason.
  - `GET /api/projects`, `POST /api/projects` (create; auto-appends `order`), `GET /api/projects/{id}`,
    `PATCH /api/projects/{id}` — the **Project** (top-level game). One PATCH serves rename,
    Settings (`dimension`/`genre` + `character_traits` JSON), Systems (`systems` JSON), and
    Preview (`hud_layout` JSON).
  - `GET /api/levels` (optional `?project_id=` filter), `POST /api/levels` (create; auto-appends
    `order`, takes `project_id`), `GET /api/levels/{id}`, `PATCH /api/levels/{id}` (rename) — the
    project's Levels list + per-level hub. `GET /api/levels/{id}/characters` returns the level's
    cast **deduced from dialogue speakers** (`Dialogue.character` where `scene.level == level`),
    each with the lines they speak — powers `LevelCharactersPage`.
  - **Characters** (per-project): `GET /api/characters` (optional `?project_id=` filter),
    `POST /api/characters` (create; name/description/project_id), `GET /api/characters/{id}`
    (detail = description + `related` list + `traits`), `PATCH /api/characters/{id}`
    (name/description/`traits`). No trait endpoints of their own — traits ride on these two
    PATCHes, and the API stores their JSON verbatim (validation lives in the frontend's
    `characterTraits.ts`, like `systems`).
    **Directed relationships**: `POST /api/characters/{id}/relationships` (`other_id`+`relationship`;
    creates a `from→to` edge, upserts on that ordered pair, validates same-project/no-self),
    `DELETE /api/characters/{id}/relationships/{rel_id}`.
    **Portrait**: `POST /api/characters/{id}/image` (multipart `file`; uploads to S3) and
    `POST /api/characters/{id}/generate-image` (`{prompt?}`; FLUX/fal.ai → S3). Each image is stored
    under a per-project/per-character folder `Characters/Project-<pid>/character-<cid>/<uuid>.<ext>`
    (unique filename, so a folder can hold many portraits); the object key is the source of truth,
    persisted on `Character.image_key`. The bucket stays **private** — the browser-facing
    `image_url` in every character response is a short-lived **presigned GET URL** derived from
    `image_key` at read time (never stored), so it can't go stale.
    Both return the character detail; both return **503** with a friendly message when the relevant
    credentials are unset/placeholder (see services below).
  - Dialogue editor also uses: `GET /api/scenes`, `GET /api/dialogues?scene_id=` (a scene's roots —
    nodes with no incoming edges), `GET /api/dialogues/{id}` (node + its `responses` + `parents`),
    `GET /api/scenes/{id}/dialogues` (**all** nodes in a scene, flat — powers the Tree view; each
    node has `id`/`title`/`parent_ids`/`text`/`character`/`requirements`/`effects`),
    `POST /api/dialogues` (create; `scene_id`/`parent_id`/`character_id`/`text`/`requirements`/
    `effects` — `parent_id` attaches it as a response of another node), `PATCH /api/dialogues/{id}`
    (partial update), `POST /api/dialogues/{id}/link` (`target_id`+`option_label`; attaches an
    *existing* node as an additional response of another node — no new row, just a new edge —
    the mechanism for two branches converging back onto the same node).
  - `GET /api/user` / `PATCH /api/user` — the **current user**. No real auth yet, so this is a
    single default user (created on first access via `_current_user()`); it stores per-user
    settings like the UI `theme`.
  - Interactive API docs (Swagger UI) at `/api/docs`; OpenAPI at `/api/openapi.json` (drives the
    frontend's `gen:api`).
- **Character images** (`api/services/`): `storage.py` uploads image bytes to **AWS S3**
  (`upload_image`, `is_configured`) and `imagegen.py` generates a portrait with **FLUX via fal.ai**
  (`generate_image`, `is_configured`; calls fal's sync endpoint, downloads the result, and hands
  the bytes back for S3 upload — swap providers by editing just this file). Both are **env-driven**
  and treat blank/`REPLACE_ME` values as "not configured":
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_REGION`/`AWS_S3_BUCKET`/`AWS_S3_PUBLIC_BASE_URL`
  and `FAL_KEY`/`FAL_IMAGE_MODEL` (in `backend/.env`, see `.env.example`). Deps: `boto3`, `requests`. `upload_image(...)` returns `(public_url, key)` and
  takes a `key_prefix` folder (the API passes `Characters/Project-<pid>/character-<cid>`); only the
  S3 key is stored (`Character.image_key`). `view_url(key)` returns the browser URL for a key — the
  `AWS_S3_PUBLIC_BASE_URL` CDN base if set, otherwise a **presigned** GET URL for the private
  bucket. The S3 client pins the **regional** endpoint (`s3.<region>.amazonaws.com`) + virtual
  addressing so presigned URLs don't hit a 307 region-redirect that breaks the SigV4 signature —
  **`AWS_REGION` must match the bucket's actual region.**
- **Yarn import/export** (`api/services/yarn_import.py`, `yarn_export.py`): `POST
  /api/scenes/{id}/import-yarn` (`text`, optional `parent_id` to attach the first pasted node to
  an existing one instead of a fresh root) parses a **bounded subset** of Yarn — `title:`/`---`/
  `===` blocks, `Speaker: text` lines, `-> option` (inline body or `<<jump Target>>`, resolved
  against both the pasted batch and existing node titles so branches can converge onto content
  that's already there), and `<<if>>`/`<<set>>` mapped onto the `Dialogue.requirements`/`effects`
  vocabulary below (see the module docstring for exactly what's supported). Anything outside that
  subset is reported as a warning and skipped; a bad jump target aborts the *whole* import (one DB
  transaction — never leaves orphaned nodes). `GET /api/scenes/{id}/export-yarn` walks the graph
  back the other way: straight, unbranched chains collapse into one Yarn node's consecutive lines,
  and a new `title:` block (using the dialogue's own `title`) starts only at branch or convergence
  points, referenced by a real `<<jump>>` — never inlined, so every node appears in the output
  exactly once. Deliberately does **not** emit `<<declare $var = ...>>` headers — `Project.
  state_schema` has the info, but scenes commonly share state keys, and declaring the same
  variable twice across multiple `.yarn` files loaded into one Yarn Spinner project is a compile
  error; add declares by hand (or export project variables once, if that's built later).
- `api/models.py`: `Project → Level → Scene` (FKs), `Character` (now `project` FK + `description`
  + `image_key` + `traits` JSONB; `Scene ↔ Character` M2M), `CharacterRelationship` (directed labeled edge
  `from_character → to_character` with a `uniq_char_relationship` unique constraint; a character's
  outgoing links are `relationships_out`), and `Dialogue` — a node in a branching dialogue
  **graph** (`scene` FK, `character` FK, `text`, plus `requirements`/`effects` JSONB lists of typed
  dicts — `has_item`/`stat_check`/`state_equals`/`remembered_choice` and `give_item`/`remove_item`/
  `change_stat`/`set_flag`/`remember_choice` — a vocabulary deliberately bounded to what Yarn's
  `<<if>>`/`<<set>>` can express, so a non-coder's "only show if…"/"when chosen, do…" pickers stay
  simple). `title` is a stable, project-wide-unique, Yarn-friendly identifier: auto-generated from
  the parent's title (or the scene) plus a running number, unless a `remember_choice` effect is
  present, in which case it tracks that effect's `state_key` instead (`Dialogue.create_node()` /
  `sync_title_from_effects()` — shared by both the API and `seed_dialogue`). Nodes are linked by
  **`DialogueEdge`** (`from_node`/`to_node` FKs, `order`, `option_label` — overrides the response's
  displayed text, falling back to `to_node.text` when blank) rather than a single `parent` FK, so a
  node can be reached from more than one place (reuse/reconvergence) or form a loop; a scene's
  roots are nodes with no `incoming_edges`.
  **`Project`** is the top-level game container: `name`/`order` plus first-class `dimension` and
  `genre` columns, and **JSONB** fields — `systems` (the per-system enabled+answers, shape
  defined by `gameSystems.ts`), `hud_layout` (`{systemId: {x,y}}`), and `character_traits` (the
  project's default character traits: a list of `{key,label,type,min,max,step,unit,default}`
  definitions). Hybrid on purpose: the
  evolving question set stays in frontend code, so its *answers* live in JSON to avoid a migration
  per question; only stable `dimension`/`genre` are columns. Traits go one step further and store
  the *definition* too, since traits can be user-invented (see the frontend Character-traits
  bullet). `Character.traits` is the matching per-character half:
  `{"values": {key: value}, "own": [definition, …]}` — an override of a project default, or a
  trait only that character has. `User` holds per-user settings
  (currently `theme`); no auth yet, so a single default user.
- Database: Postgres via `DATABASES['default']` (psycopg 3), params from `POSTGRES_*` env vars
  (defaults target the local `game_editor` db/role). Migrations **are** applied; seed demo
  dialogue data with `python manage.py seed_dialogue`.
- **CORS is active** (`django-cors-headers`): allowed origins come from `DJANGO_CORS_ORIGINS`
  (defaults to the Vite dev server). Add new origins there.
- Add endpoints on the `api` object in `api/api.py`; use Ninja `Schema` classes for I/O. After
  changing a schema, regenerate the frontend types (`npm run gen:api`).

### MCP server (`backend/mcp_server/`)
An **MCP** server exposing the API as tools for an AI game-creation agent (`python -m mcp_server`,
stdio; see its README for client wiring). It's a **client of the REST API over HTTP**, not a Django
app — `client.py` is a thin httpx wrapper (`GAME_EDITOR_API_URL`, default
`http://127.0.0.1:8000/api`), so tools can't bypass endpoint validation and the backend must be
running. `server.py` holds a `FastMCP` instance with ~34 read/create/update tools mirroring the
hierarchy (projects · levels · locations · scenes · characters · character traits · story state ·
dialogue, incl. `import_scene_yarn`/`export_scene_yarn`), three resources (`game-editor://projects`,
`…/projects/{id}` = project+levels+scenes+characters, `…/scenes/{id}/yarn`) and a `build-game`
prompt. **Tool docstrings are the agent-facing docs** — the requirement/effect vocabulary spelled
out in `create_dialogue` must stay in sync with `DialogueRequirement`/`DialogueEffect` in
`frontend/src/api/client.ts` (every entry keys off `state_key`; `change_stat` uses `amount`).
`register_state_variable` and the six `*_character_trait(s)` tools compose instead of proxying
(GET + PATCH of `project.state_schema` / `project.character_traits` / `character.traits`) so the
agent never hand-assembles those JSON blobs: `register_state_variable` uses the UI's
`flag_`/`choice_`/`item_`/`stat_` key convention, and the trait tools share the frontend's
`traitKey()` slug rule via `_slug()` and do the project-defaults overlay in
`get_character_traits`. No delete tools are exposed on purpose (the two `remove_*_trait` tools
clear fields, not rows).

## Conventions

- **Frontend: TypeScript everywhere.** Keep components small and single-purpose.
- **Backend: Python/Django.** Keep API logic in `api/`; use Django Ninja `Schema`s for I/O.
  Settings are env-driven — add new config as `os.getenv(...)` with a sane local default and
  document it in `.env.example`.
- **Shapes are outlines:** render with `fill="none"` and a visible `stroke`.
- Coordinates/sizes live on the `Shape` model (`x`, `y`, `width`, `height`); keep geometry math
  in the canvas/shape layer.
- **Frontend↔backend is typed end-to-end**: change a Ninja schema → run `npm run gen:api` →
  consume the regenerated types via `src/api/client.ts`. Don't hand-write API response types.
- The root `.npmrc` sets `legacy-peer-deps=true` because `openapi-typescript@7` still declares a
  `typescript@^5` peer while we're on TS 6 (works fine). Keep it until that peer range updates.

## Common commands

```bash
# Frontend (from repo root)
npm install            # install frontend workspace
npm run dev            # frontend + backend together (concurrently)
npm run dev:web        # frontend only (http://localhost:5173)
npm run build          # build frontend
npm run gen:api -w frontend   # regenerate src/api/schema.d.ts from the API (backend must be up)

# Backend (from backend/, venv at backend/.venv)
./.venv/bin/python manage.py runserver        # serve on :8000  (== npm run dev:api)
./.venv/bin/python manage.py makemigrations api && ./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py seed_dialogue    # seed demo dialogue tree
./.venv/bin/pip install -r requirements.txt   # (re)install backend deps
./.venv/bin/python -m mcp_server              # MCP server over stdio (API must be running)
```

Postgres runs as a Homebrew service: `brew services start|stop postgresql@14`.

## Data models

Frontend shape model (`frontend/src/types.ts`):
```ts
type ShapeType = 'rectangle' | 'ellipse';
interface Shape { id: string; type: ShapeType; x: number; y: number; width: number; height: number; }
```

Backend dialogue graph (`backend/api/models.py`):
```python
class Dialogue(models.Model):
    scene = ForeignKey(Scene, null=True, related_name="dialogues")
    title = CharField(unique=True)                     # stable, Yarn-friendly id (auto-generated)
    character = ForeignKey(Character, null=True, related_name="dialogues")
    text = TextField(blank=True, default="")
    requirements = JSONField(default=list, blank=True)  # gate: only show this response if...
    effects = JSONField(default=list, blank=True)       # when chosen: do...

class DialogueEdge(models.Model):
    from_node = ForeignKey(Dialogue, related_name="outgoing_edges")
    to_node = ForeignKey(Dialogue, related_name="incoming_edges")
    option_label = CharField(blank=True, default="")    # "" -> falls back to to_node.text
    order = PositiveIntegerField(default=0)
```
A scene's roots are `Dialogue`s with no `incoming_edges`.

## Deliberately out of scope (for now)

Real auth, persistence, multiplayer, resize/rotate handles, zoom/pan, undo/redo. SVG was chosen
for simplicity; migrating to a canvas renderer (e.g. react-konva) is a known future option when
shape counts get large.
