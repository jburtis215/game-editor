# game-editor — Platform Vision & Roadmap

*Drafted July 2026. This is the product north star; CLAUDE.md stays the technical
reference for what exists today.*

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
- Systems architect: 7 systems (incl. Movement) with typed questions, live
  micro-simulation vignettes sharing one math module (`systemSimMath.ts`), blueprint
  manifest (`buildManifest()`, copy-only).
- Characters with descriptions, directed relationships, FLUX-generated portraits in S3
  (presigned URLs).
- HUD layout mockup (Preview tab). Typed end-to-end API (Django Ninja → openapi-fetch).

## Roadmap

Each phase is small, ships on its own, and activates a piece of the story above.

### Phase 1 — Unified project export (the source of truth becomes an artifact)
*Everything else layers on this. No new UI beyond a button.*

- [ ] `GET /api/projects/{id}/export` merging: systems manifest + dimension/genre +
      `state_schema` (as declared variables) + all characters & relationships + the full
      Level → Scene → Dialogue/Edge graph (reuse `yarn_export`'s walker project-wide,
      which also solves the cross-scene `<<declare>>` collision).
- [ ] Version the format from day one: `"format": "gameblueprint/0.1"`. Treat it as a
      contract.
- [ ] Fold each system's **derived numbers + plain-language takeaways** from
      `systemSimMath.ts` into the export ("a careless player dies in ~8 hits") — design
      intent in words, the highest-signal input an agent can get.
- [ ] Download button on the Systems tab (replaces copy-only manifest).

### Phase 2 — MCP read server (activates "brief the engineer")
- [ ] Thin MCP server (Python SDK) over the existing Django API/DB. Start with 3–4 read
      tools: `get_blueprint`, `get_system_config(id)`, `get_dialogue_scene(id)`,
      `get_character(id)` (include portrait presigned URL).
- [ ] Per-user/project auth tokens.
- [ ] Validate with the target demo: point Claude Code at an empty Godot project +
      the server; "build the tavern scene"; confirm it pulls real design facts instead
      of inventing them.
- [ ] `get_build_plan` tool (+ a `plan.md` section in the Phase-1 export): a
      **deterministic** build order — topological sort over known dependencies
      (foundation systems before scoped extensions, health before combat, state schema
      before the dialogue that reads it, characters before the scenes that cast them),
      rendered as templated prose the same way sim takeaways are. No LLM on our side:
      we serve the skeleton; the creator's agent adapts it to engine specifics. Once
      Phase 3 lands, filter by `build_status` so the plan is always live. Ship a
      `/kickoff` MCP prompt alongside it.

### Phase 3 — Build truth flows back (activates the supervisor)
- [ ] `build_status` field on design objects (dialogue scenes, systems, characters):
      designed / in-progress / built / verified. Write tool `set_build_status`.
- [ ] `report_deviation` write tool + pending-deviations model + reconcile UI
      (accept-into-design / flag-for-rework).
- [ ] `post_build_snapshot` write tool → S3 (reuse `storage.py` pipeline) → snapshots
      render in the "best available representation" slot next to design mockups.
- [ ] Project-home rollup: % built, pending deviations count, latest snapshots.

### Phase 4 — The reconcile ritual + intent capture
- [ ] Publish the `/sync-check` MCP prompt; `get_design_values` diff-support tool.
- [ ] Intent layer in the platform (and export): per-project references/touchstones
      ("combat like Hades"), decision rationale on answers, anti-goals ("no fail
      states"), and a pacing/beat map over the Level → Scene structure.
- [ ] Blueprint health check: unreachable dialogue requirements, state keys set but
      never read, enabled-but-unconfigured systems — a readiness meter, because a
      source of truth that can be self-contradictory isn't one.

### Phase 5 — Engine-specific demos (marketing, not product)
*Order: Godot first, then UEFN/Verse, then Roblox. Godot is the cheapest proof
(all-text formats — `.tscn`/`.tres`/GDScript; Yarn Spinner runtime exists) and doubles
as the Phase-2 validation environment. Fortnite and Roblox are the long-term reach
targets and should both be covered eventually.*

- [ ] Godot demo: agent + MCP server scaffold a playable scene from the blueprint
      (dialogue via Yarn Spinner, systems as generated config/resources).
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
