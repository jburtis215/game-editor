# game-editor — Platform Vision & Roadmap

*Drafted July 2026; roadmap revised August 2026 after the MCP authoring server shipped.
This is the product north star; CLAUDE.md stays the technical reference for what exists
today.*

## One-line pitch

A Figma-like **game design platform for non-coders** that becomes the **source of truth
an AI coding agent builds from** — preproduction planning tool first, live production
dashboard second.

## The core insight

AI agents (Claude Code, Cursor, etc.) are becoming how low-code creators build games
inside real engines. Those agents are good at writing code and bad at knowing what *your*
game should be — left unguided, they fill every design gap with plausible genre defaults.
The scarce input isn't code; it's **captured design intent**: decisions, numbers,
characters, dialogue, references, and the *why* behind them.

This platform captures that intent in structured form, then serves it to whatever agent
the creator uses, in whatever engine they target. We never call an LLM ourselves and we
don't build the game — we are the design brain the creator's agent consults.

## The lifecycle framing

The same data serves three eras of a project:

1. **Preproduction — plan and *feel* the game before it exists.**
   Settings/Systems questionnaires, branching dialogue, characters, HUD mockups — plus
   **paper prototypes**: the Systems-tab micro-simulations (giant-bops-knight, spacebar
   jump) that let a creator feel a design decision with zero production. Uploaded
   concept art and reference boards belong here too.

2. **Production — live overview and supervisor of the "engineer" (the agent).**
   A supervisor does three things, and each is a concrete feature:
   - **Briefs the engineer** — the agent pulls specs via MCP read tools instead of guessing.
   - **Reviews the work** — build screenshots/clips land next to design mockups;
     engine-side changes arrive as *deviation proposals* the creator accepts or rejects.
   - **Tracks completion** — every design object carries a status the agent updates
     (designed → in progress → built → verified), rolling up to "your game is 60% built."

3. **The connective principle: "best available representation."**
   Every design object has one display slot showing the most real thing we have. The
   combat sim vignette holds the slot until a real gameplay clip replaces it; a FLUX
   portrait holds it until an in-engine screenshot arrives; the draggable HUD mockup
   until a build screenshot. Layouts never change — reality progressively overwrites
   the paper prototype.

## Architecture of the loop

```
game-editor platform      canonical design, state, assets (Postgres + S3)
        ↕
MCP server                thin layer over the existing Django API
        ↕
AI coding agent           Claude Code / Cursor / Copilot — the creator's "engineer"
        ↕
game engine               UEFN / Godot / Roblox / …
```

- **Design intent flows down** (read tools): `get_blueprint`, `get_system_config`,
  `get_dialogue_scene`, `get_character` …
- **Build truth flows back up** (write tools): `report_deviation`, `post_build_snapshot`,
  `set_build_status` …
- One server implementation, hosted by us; a per-creator auth token scopes it to their
  project. The creator adds one config line to their agent. Token efficiency comes from
  *retrieval on demand*, not context preloading — the agent pulls only the slice of the
  design relevant to its current task.

### Rules that keep the platform trustworthy

- **The platform is canonical.** Engine-side changes never silently overwrite design.
  They arrive as pending deviations ("build uses gravity 150%, design says 100%") that
  the creator reconciles with one click — accept into design, or flag for rework.
  Effectively a pull-request model for game design.
- **The reconcile ritual.** The platform only knows what agents report; hand-edits in
  the engine are invisible until compared. So the MCP server ships a **reconcile flow**:
  a `get_design_values` tool plus a published MCP *prompt* (`/sync-check`) that instructs
  the agent to diff design vs. actual project files and `report_deviation` for each
  mismatch. Run at session start or whenever a system's files are touched.
- **Honest boundary:** no engine-side daemons or per-engine plugins. Agent-mediated
  only. Fine for the target audience (creators working through their agent), but drift
  from purely-manual edits is undetected until the next reconcile.

## What exists today (foundation)

- Project → Levels → Scenes → branching dialogue **graph** (requirements/effects
  vocabulary deliberately bounded to Yarn `<<if>>`/`<<set>>`), per-scene Yarn
  import/export.
- **Story state**: a `Project.state_schema` registry (flags / remembered choices /
  items / stats). The dialogue editor's requirement/effect pickers auto-register keys,
  and a requirement can only reference state an effect has already registered — never a
  freehand key.
- Systems architect: 7 systems (incl. Movement) with typed questions, live
  micro-simulation vignettes sharing one math module (`systemSimMath.ts`), blueprint
  manifest (`buildManifest()`, still copy-only — see Phase 1).
- Characters with descriptions, directed relationships, typed **traits** (project
  defaults overlaid live, plus per-character overrides and own traits), and uploaded or
  FLUX-generated portraits in S3 (presigned URLs).
- **Locations** per level: manually-cast places with kind/scale/mood/props, reference
  imagery, and a **connection graph** (labeled, optionally requirement-locked exits —
  lock-and-key design), each listing the scenes set there.
- **Abilities**: the player's verb set as project-scoped rows, each with invented
  `params` and an optional unlock requirement.
- **Level layout**: an ASCII tile grid per level (`Level.layout`) painted in
  `LevelLayoutPage`, over a project-scoped `EntityType` palette (glyph + bounded
  `behavior` + sprite). One cell = one game unit, so a 3-unit jump clears a 3-cell wall.
- **Blueprint export**: `GET /api/projects/{id}/export` serves the `gameblueprint/0.1`
  document (contract in `docs/blueprint-schema.md`), including derived feel numbers and
  their plain-language takeaways. Downloadable from the Systems tab.
- HUD layout mockup (Preview tab). Typed end-to-end API (Django Ninja → openapi-fetch).
- **MCP authoring server** (`backend/mcp_server/`): ~40 tools, 3 resources, and a
  `build-game` prompt, all as a thin client of the REST API. The original Phase 2
  arrived early — but as a *write* surface. An agent can author an entire game plan,
  yet still can't *read* the plan back out: the export exists over REST, but no tool
  serves it, and no tool exposes level layouts or the entity palette at all. Closing
  that read side is the remaining half of Phase 1.

## Roadmap

*Re-sequenced August 2026: the MCP server shipped ahead of schedule as an authoring
surface, so the phases below reorder around the real remaining gap — consumption, then
the semantic holes an agent would otherwise fill with guesses. Each phase is still
small, ships on its own, and activates a piece of the story above.*

### Phase 1 — Blueprint export + MCP read layer (activates "brief the engineer")
*Everything else layers on this. Merges the old Phases 1 and 2, minus the server that
already exists. **Shipped** (Aug 2026): the export endpoint, the derived-numbers port, the
level/entity data model, the MCP read layer, and the addressing/manifest layer. `build_plan`
was dropped rather than built (see below). What remains is the shared TS↔Python definitions
and validating the whole thing against a real engine build.*

- [x] `GET /api/projects/{id}/export` → one versioned `"format": "gameblueprint/0.1"`
      document (treat it as a contract). Shipped: dimension/genre, per-system answers
      with **derived numbers + plain-language takeaways** (`services/derived.py`, a port
      of `systemSimMath.ts` — "a careless player dies in ~2 hits"), `state_schema`,
      characters + relationships + portrait URLs, the entity palette, the tile legend,
      and every level's layout grid, flattened entity coordinates, `intro_scene_id`,
      `on_complete`, and full Scene → dialogue graph. Contract in
      `docs/blueprint-schema.md` — **change both together**.
- [x] **Export gaps closed** (Aug 2026): `locations[]` per level with detail fields +
      connections · top-level `abilities[]` · character **resolved traits** (project defaults
      overlaid, mirroring `characterTraits.ts`) · `hud_layout` · per-scene Yarn text via the
      existing exporter · `state_schema` as a single `yarn_declarations` block (solves the
      cross-scene `<<declare>>` collision documented in `yarn_export.py`). Every
      `CREATIVE-LEVERS` "Export:" line that isn't waiting on `build_plan` is now done.
- [ ] **Where definitions live:** extract the system/genre/dimension data from
      `gameSystems.ts` into a shared `shared/gameSystems.json` consumed by both TS and
      Python. `derived.py` is currently a **hand-port** of `systemSimMath.ts` with no
      parity test — the two can silently drift, which is exactly the failure this item
      prevents. (Persisting a frontend-computed manifest was rejected: MCP agents PATCH
      `systems` directly and would silently stale it — derive at read time.)
- [ ] Remaining backend services: `system_defs.py` (load the JSON, `build_manifest()`),
      `declarations_for()` in `yarn_export.py`. Seeds backend test infra: TS↔Python
      parity fixtures on manifest + takeaway strings, build-plan ordering invariants.
      *(`blueprint.py` and `derived.py` exist; `sim_math.py` shipped as `derived.py`.)*
- [x] ~~`get_build_plan`: a deterministic build order — topological sort…~~ **Dropped
      (Aug 2026)**, replaced by `get_manifest` + addresses/hashes. The creator directs their
      own agent ("do movement first"), so an order *we* compute is a third opinion competing
      with theirs, and "health before combat" is a notch this platform shouldn't have. What
      an agent actually needs is a **map, not a route**: every object with a stable address,
      a summary, a hash, and the dependencies the design genuinely *entails* — a locked exit
      needs its key, a scene needs its cast. Same information, no invented sequence, and
      nothing fights the creator when they specify one. See `api/services/manifest.py`.
- [x] **Addresses + hashes** (Aug 2026): every design object carries a readable address
      (`entity:goomba`) that follows renames, and a content hash. These are what make the
      rest of the loop possible — without a shared name for a thing, "I built the walker"
      and "does the walker still match?" have no common referent, and drift is undetectable.
      The hash gives **staleness detection for free**: once an agent reports building
      against a hash, the platform alone can tell that the design has since changed, with no
      engine access and no reconcile pass. `api/services/addressing.py`.
- [x] MCP **read layer** (Aug 2026): `get_blueprint`, `get_game_config`,
      `get_level_design` and `list_entity_types` — each a slice of the export, refetched per
      call so an agent never builds from a stale design — plus a
      `game-editor://projects/{id}/blueprint` resource, the `kickoff` prompt ("read the
      blueprint, follow the plan, never invent values the design already answers"), and the
      project resource rebuilt on top of the export. `get_build_plan` is the one read tool
      still missing; it lands with the item above.
      *(Also: `mcp` + `httpx` were never declared as dependencies — the server had never
      been run. Now in `requirements.txt`, with `mcp` pinned `<2`.)*
- [x] "Download blueprint" button on the Systems tab (augments the copy-only manifest).
- [ ] Validate with the target demo: point Claude Code at an empty Godot project + the
      server; "build level 1"; confirm it pulls real design facts instead of inventing
      them.

### Phase 2 — Semantic model gaps (makes the blueprint unambiguous)
*Holes a building agent currently has to fill with plausible genre defaults — the exact
failure mode this platform exists to prevent. The full design-vocabulary expansion
(world map, verbs/3Cs, encounters, triggers, art direction) is specified with
actionable steps in `CREATIVE-LEVERS.md`; the items below are its prerequisites.*

- [ ] **Player character + tags.** Systems carry `scope: player|tagged`, but no
      character is marked as the player and there is no tag field to satisfy `tagged`.
      Add a player designation + `Character.tags`; surface both in export and MCP.
- [ ] **Quests / objectives.** No model for goals, win/lose conditions, or progression
      beyond level `order`. Add a Quest/Objective model tied to existing `state_schema`
      keys ("flag X set", "item Y held", "stat Z ≥ N" — reusing the bounded
      requirements vocabulary), with API + MCP tools + a project tab.
- [ ] **First-class items.** Items exist only as opaque `item_*` state keys —
      `item_cellar_key` teaches the agent nothing beyond its label. Extend state
      entries (or add a small Item model) with description/properties.
- [ ] **Intent capture** (promoted from the old Phase 4): `description` on Project and
      Level (today neither has one), per-project references/touchstones ("combat like
      Hades"), and anti-goals ("no fail states") — all folded into the export.

### Phase 3 — Agent correction & integrity tools
*An authoring agent can't currently fix its own structural mistakes.*

- [ ] DELETE endpoints + MCP tools for dialogue nodes, edges (unlink), scenes, levels,
      and characters — today only locations and relationships are deletable.
- [ ] MCP parity gaps: an `update_scene` tool (the PATCH endpoint exists, no tool),
      edge reordering, `option_label` clearing.
- [ ] Blueprint health check (moved from the old Phase 4): unreachable dialogue
      requirements, state keys set but never read, enabled-but-unconfigured systems —
      a readiness meter, because a source of truth that can be self-contradictory
      isn't one.
- [ ] `Dialogue.title` is unique **globally**; make it unique per project before
      projects multiply and titles collide.

### Phase 4 — Build truth flows back (activates the supervisor)
*Now unblocked by addresses + hashes: an agent can finally name the thing it built and say
which version of the design it built from. Godot is the only target for now — deliberately,
since engine-specific conventions do more for the agent's efficiency than any additional
data we could serve.*

- [x] **Godot conventions** (Aug 2026, `mcp_server/conventions.py` +
      `get_engine_conventions`): units (one cell = one design unit = 32 px, so the derived
      numbers convert mechanically), file layout per address type, node types, tile
      semantics (`=` is a one-way *tile property*; `P`/`G` are not tiles), entity behavior,
      and `game_editor_sync.json`. Prescriptive **only** where reconciliation needs it —
      a layout that varies session to session makes "not built" indistinguishable from
      "not found", which silently breaks the return half of the loop.
- [x] **Dialogue runtime decided**: a small GDScript player over the `dialogue` graph, not
      Yarn Spinner — the official GDScript port requires Godot 4.6+ and is alpha ("we do not
      recommend you use this to ship a game just yet") and the C# port is an unsupported beta
      needing the .NET build. The `.yarn` files are still written, so adopting the addon
      later is a drop-in. This only works because the export carries dialogue in *both*
      forms, and the runner is small only because the requirement/effect vocabulary was
      bounded in the first place.

- [x] `report_built(address, engine_path, hash)` (Aug 2026) — the write half of the loop,
      plus `get_build_status`. Staleness works exactly as hoped: an object whose design hash
      differs from the one it was built against is stale, detected with **no engine access
      at all**. Renames surface the same way — the record follows the object, so a build
      filed under an old address reports back that the engine artifact needs renaming.
      An address that names nothing is rejected, so an invented address can't file a report
      nothing will ever match.
- [x] `build_status`: not_built / in_progress / built / verified, derived from the reports
      rather than set by hand, with `stale` and `renamed` computed at read time.
      `percent_built` counts only built-**and**-current objects — a stale build is work still
      owed. Orphaned reports (design object deleted, engine file left behind) are surfaced
      rather than hidden.
- [ ] **Policy — decided:** engine changes that *contradict* the design arrive as pending
      deviations the creator accepts or rejects. Values the design never specified (the
      agent had to invent one) are recorded as design, flagged as originating in the build —
      nothing is being overwritten, and the design gets more complete rather than drifting.
- [ ] `report_deviation` write tool + pending-deviations model + reconcile UI
      (accept-into-design / flag-for-rework), keyed by address — including **field**
      addresses (`system:movement.gravity`) so a mismatch names exactly one value.
- [ ] `get_design_values`: the same design as a **flat** list of `{address, value}` rows.
      The nested blueprint is right for comprehension and wrong for diffing; `/sync-check`
      needs something a mechanical comparison can walk.
- [ ] `post_build_snapshot` write tool → S3 (reuse `storage.py` pipeline) → snapshots
      render in the "best available representation" slot next to design mockups.
- [ ] Project-home rollup: % built, pending deviations count, latest snapshots.
- [ ] The reconcile ritual: publish the `/sync-check` MCP prompt + the
      `get_design_values` diff-support tool.
- [ ] Per-creator project auth tokens for the hosted MCP server (prereq for sharing the
      loop beyond localhost).

### Phase 5 — Engine-specific demos (marketing, not product)
*Order: Godot first, then UEFN/Verse, then Roblox. Godot is the cheapest proof
(all-text formats — `.tscn`/`.tres`/GDScript; Yarn Spinner runtime exists) and doubles
as the Phase-1 validation environment. Fortnite and Roblox are the long-term reach
targets and should both be covered eventually.*

- [ ] Godot demo: agent + MCP server scaffold a playable scene from the blueprint (systems
      as a generated config autoload, dialogue via the GDScript runner — see Phase 4).
      Target: **Godot 4.4**, the platformer project.
- [ ] Verse/UEFN codegen prototype off the Phase-1 export: `game_config.verse`
      (systems → typed constants/classes) + dialogue → Verse state machine. Scope
      honestly: creators wire generated modules to devices themselves; no custom
      dialogue UI generation.
- [ ] Roblox: revisit once the loop is proven — Open Cloud APIs make it the one
      ecosystem where integration can be a push pipeline rather than dropped files.

## Deliberately out of scope

- Running or rendering the actual game (we are not a runtime or engine).
- Engine plugins / file watchers; anything not agent-mediated.
- Calling LLMs ourselves; managing or paying for creators' AI usage.
- Real-time multiplayer editing, auth hardening, billing — until the loop above is
  proven end-to-end.
