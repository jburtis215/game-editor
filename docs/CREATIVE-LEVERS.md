# Creative levers — the game-planning features that give creators real control

*Drafted August 2026. Companion to `VISION.md`. That doc sequences the platform
infrastructure (export, MCP read layer, feedback loop); this one specifies the missing
**design vocabulary** — the domains a creator currently cannot plan, so the building
agent fills them with genre defaults. The pattern behind all five: today the platform
plans story and systems tuning in detail, but cannot plan **space, action, or
opposition** — the three things most games actually are.*

*None of this is invented vocabulary — each lever is a long-established game-design
discipline given a structured, agent-readable form. The platform is, in effect, a
**living game design document (GDD)**: the classic preproduction artifact, kept
machine-consumable. Section headers name the tradition each lever comes from.*

*Ranked by creative-control-per-effort. Everything here depends on VISION Phase 1 (the
blueprint export) to reach the agent; each section notes what it reuses from existing
machinery — most of these are new attachment points for patterns that already exist
(`DialogueEdge`, the questionnaire format, the S3 image pipeline, the bounded
requirements/effects vocabulary).*

---

## 1. The world layer — locations as a connected, detailed map

**Design tradition:** the room-and-exit graph is the oldest structure in game design —
interactive fiction (Zork) modeled the world as rooms connected by labeled, sometimes
locked exits, and modern level design still plans this way. Gated connections are
textbook **lock-and-key design** (the Metroidvania/Zelda "boss key" pattern: the
world's shape *is* the progression). Props and mood are **environmental storytelling**;
the sketch-canvas note below is a **blockout/greybox**, the standard first pass of
level design.

**Why:** `Location` today is a name + description + cast — a narrative grouping, not a
place. An agent asked to "build the tavern" invents its size, exits, contents, and
mood. Connections turn the flat location list into a world *graph*: traversal order,
gating, and pacing all become plannable, and the build plan can walk it — the
**critical path** and its optional branches become visible.

### 1a. Location connections (structurally identical to `DialogueEdge`)

- [x] Model `LocationConnection`: `from_location` / `to_location` FKs, `label`
      ("cellar door"), `bidirectional` bool (default true), `requirements` JSONB —
      the **same** bounded vocabulary as `Dialogue.requirements` ("locked until
      `item_cellar_key`"), plus a unique constraint on the ordered pair.
- [x] API: `POST /api/locations/{id}/connections` (`to_id`, `label`, `requirements`),
      `DELETE /api/locations/{id}/connections/{conn_id}`; connections included in
      `GET /api/locations` rows. Validate same-level (or same-project if cross-level
      travel is wanted — decide then; start same-level).
- [x] MCP: `connect_locations` tool (+ include connections in `list_locations`).
- [x] UI: on each `LocationsPage` card, a "Connects to…" row — picker of the level's
      other locations + optional requirement via the existing `MemoryComboBox`.
- [ ] Export: `levels[].locations[].connections`; `build_plan` orders locations by a
      BFS from the unlocked subgraph so gated areas build after their keys exist.
      *(deferred — no export layer yet)*

### 1b. Location detail fields

- [x] Columns on `Location`: `kind` ("interior"/"exterior"/""), `scale`
      ("cramped"/"room"/"open"/"vast"/""), `mood` (free text — "smoky, candle-lit,
      too quiet"), `props` JSONB list of strings ("bar counter", "trapdoor behind the
      barrels"). Props are where the creator's mental image lives and exactly what
      agents currently hallucinate.
- [x] API/MCP: extend the existing `PATCH /api/locations/{id}` schema + the
      `create_location`/`list_locations` tools — no new endpoints.
- [x] UI: fields on the `LocationsPage` card (kind/scale as small selects, mood as a
      one-line input, props as a chip list). Debounce saves ~400ms like Settings.
- [ ] Export: all four fields on each location object. *(deferred — no export layer yet)*

### 1c. Location reference imagery (generalize the portrait pipeline)

- [x] Reuse `api/services/storage.py` + `imagegen.py` verbatim: add
      `Location.image_key`, `POST /api/locations/{id}/image` (upload) and
      `POST /api/locations/{id}/generate-image` (`{prompt?}` — default prompt built
      from name + description + mood, like the character version), key prefix
      `Locations/Project-<pid>/location-<lid>/`. Same 503-when-unconfigured behavior,
      same presigned `image_url` derived at read time.
- [x] MCP: `generate_location_art` tool (mirror of `generate_character_portrait`).
- [x] UI: image slot on the location card — this is the "best available
      representation" slot from VISION §3, ready for a build screenshot to replace it
      later.

### 1d. Locations bound to actual space (Aug 2026)

*The first Godot build reported every location as "transcribed as data — no cells represent
it, so it has no playable space". Mood, props, reference art and locked exits all described
somewhere the game could not point at: the whole world layer failed this doc's own test that
a lever must move the output.*

- [x] `Location.extent` (`level` | `area` | `point` | `""`) + `region`
      `{x,y,width,height}` in grid cells. `extent` is how much space a place *occupies*;
      the existing `scale` stays how big it *feels* — a "vast" hall can occupy one small
      area, so they're separate axes rather than one confused field.
- [x] API: `extent`/`region` on the existing location create/PATCH, validated against the
      level's own layout (400 when the rectangle doesn't fit). No new endpoints.
- [x] MCP: `place_location`. Export: `extent` + `region` on each location, with
      `extent: "level"` resolved to the whole grid so every placed location reads the same.
- [x] UI: an extent select on the location card, and a **Tiles ⇄ Locations** toggle on the
      layout editor — pick a place, drag a box. A 1×1 drag makes a `point`, larger makes an
      `area`; boxes may overlap and nest (a well inside a hillside), which is design, not error.
- [x] Godot conventions: a placed location builds as an `Area2D` over its region, which is
      what finally gives dialogue, encounters and connection-gating somewhere to fire.
- [ ] Not done: 3D and non-grid games. The binding is deliberately 2D-grid-only for now —
      the tile grid is the only spatial model the platform has.
- [ ] Future (note, don't build yet): the orphaned `ShapeEditorPage` is a plausible
      "block out this location" SVG floor-plan sketcher — a rough layout is a
      legitimate design artifact an agent can read.

---

## 2. The action layer — player verbs, controls, and camera

**Design tradition:** this is the industry's **3Cs — Character, Controls, Camera** —
the discipline AAA studios staff first, because everything else is felt through them.
The verb set is **verb design** (Crawford's "what does the player *do*?", Anna
Anthropy's verb-centric vocabulary); the tuning sliders around it are **game feel**
(Swink): the same jump reads floaty or heavy purely on numbers. Ability unlocks are
**ability gating**, the mechanic half of lock-and-key design.

**Why:** the Systems architect tunes numbers (jump height, run speed) but never
captures the identity-defining decision: **what can the player do?** And input style +
camera are literally the first things an agent must implement; the blueprint is silent
on both.

### 2a. Controls & Camera as an eighth system (pure questionnaire work)

- [x] Add a `controls` system to the definitions (in `gameSystems.ts` today; in
      `shared/gameSystems.json` once VISION Phase 1 lands): questions like
      `inputStyle` (single: platformer / twin-stick / point-and-click / wasd+mouse),
      `camera` (single: side-on / top-down / follow third-person / fixed rooms),
      `cameraFeel` (slider: locked → loose follow). Add per-genre defaults to
      `genreDefaults()`.
- [x] Zero new machinery: the Systems tab, `normalizeSystems()`, `buildManifest()`,
      and (post-Phase-1) the export all pick it up automatically. Optionally a small
      sim vignette later; not required to ship. *(No sim vignette built — optional.)*
- [ ] `build_plan`: controls/camera build as part of the project scaffold step — first,
      before any other system. *(deferred — no build_plan layer yet)*

### 2b. Abilities / verb set (new model — it's per-project data, not a questionnaire)

- [x] Model `Ability`: `project` FK, `name` ("Dash"), `description` (plain-language
      behavior intent — "short burst, brief invulnerability"), `params` JSONB
      (`{key: number|string|bool}` — cooldown, distance, uses), `unlock_requirements`
      JSONB (same bounded vocabulary — "unlocks when `flag_met_mentor`"; empty =
      available from the start), `order`.
- [x] API: `GET /api/abilities?project_id=`, `POST`, `PATCH /{id}`, `DELETE /{id}`.
      *(Plain delete — nothing references an `Ability` yet, so there is nothing to 409 on.)*
- [x] MCP: `list_abilities`, `create_ability`, `update_ability`.
- [x] UI: an "Abilities" panel — most naturally on the Systems tab under the movement
      system, or its own small section; card list with name/description/params +
      unlock picker (`MemoryComboBox` again). *(Its own section below the architect —
      the verb set is project-wide data, not one system's answers.)*
- [ ] Export: top-level `abilities` list; `build_plan` places abilities right after
      foundation systems and orders locked abilities after the state keys that gate
      them (same dependency logic as dialogue-after-declarations).
      *(deferred — no export layer yet)*
- [ ] This is also what progression finally *grants*: a quest reward or effect can
      reference an ability once both exist. *(the model exists; nothing grants one until
      quests/rewards do)*

---

## 3. The opposition layer — enemies and encounters

**Design tradition:** **encounter design** — the level-design sub-discipline of
placing which enemies where, under what trigger, at what pacing — plus **enemy
archetype** design. The canonical example is Pac-Man's ghosts: four enemies sharing
one mechanic, differentiated purely by plain-language behavior intent (chaser,
ambusher, fickle, random). The list of them is the classic GDD **bestiary**; their
placement over time is the **difficulty curve**.

**Why:** the combat system has modes and lethality sliders, and **no concept of an
enemy anywhere**. The sliders tune a fight the plan never describes. Characters + the
Phase 2 tags get most of the way; what's missing is behavior intent and placement.
(Combat-forward genres need this badly; dialogue-forward games barely at all — it can
trail sections 1–2.)

- [ ] `Character.behavior` text field: plain-language behavior intent ("patrols;
      charges when the player is close; flees under 20% health"). Design intent, not
      AI code — the same philosophy as sim takeaways. Rides on the existing
      `PATCH /api/characters/{id}` + `update_character` tool.
- [ ] Hostility via Phase 2 tags (`enemy`, `boss`, `neutral`) — no new field; document
      the convention in the tag picker and the MCP docstrings.
- [ ] Model `Encounter`: `location` FK, `name`, `characters` M2M (the enemies),
      `trigger_requirements` JSONB (bounded vocabulary — "only after
      `flag_alarm_raised`"; empty = on entry), `notes` text, `order`.
- [ ] API: `GET /api/encounters?location_id=`, `POST`, `PATCH /{id}`, `DELETE /{id}`.
      MCP: `list_encounters`, `create_encounter`.
- [ ] UI: an "Encounters" row on the location card (this is why the world layer ships
      first) — pick characters tagged hostile, optional trigger.
- [ ] Export: encounters nested under their location; `build_plan` orders them after
      both the combat system and the characters they cast. Combat's derived numbers
      (lethality, hits-to-die) now have named opponents to apply to.

---

## 4. World events + item logic — generalize requirements/effects beyond dialogue

**Design tradition:** every level editor since Doom has had **trigger volumes** —
"when the player enters/does X (and condition Y holds), do Z" — the backbone of level
scripting in Hammer, Unreal, and Mario Maker alike. The item side is the standard RPG
**item taxonomy** (key / consumable / equippable / quest item) that inventory design
has used since tabletop, with key items being lock-and-key design's other half.

**Why:** the bounded requirements/effects language is the platform's best asset — a
non-coder scripting language that compiles to Yarn — and today it's only reachable
from dialogue choices. New **attachment points**, not new vocabulary: same JSON shape,
same `MemoryComboBox` UI, same Yarn-compatible semantics. One mechanism upgrades
items, locations, and quests at once.

### 4a. Triggers

- [ ] Model `Trigger`: `project` FK, `event` (enum: `enter_location` /
      `pickup_item` / `quest_completed`), `subject_id` (the location/item/quest),
      `requirements` JSONB (optional gate), `effects` JSONB (what happens — "entering
      the tunnels sets `flag_heard_the_whispers`"), `note` text, `order`.
      Start with exactly these three events; resist a generic event bus.
- [ ] API: `GET /api/triggers?project_id=`, `POST`, `PATCH /{id}`, `DELETE /{id}`.
      MCP: `list_triggers`, `create_trigger` (docstring repeats the vocabulary, like
      `create_dialogue`).
- [ ] UI: surface triggers **in context**, not as a global list — an "On entering…"
      row on the location card, "When picked up…" on the item card. Reuse the
      requirement/effect pickers from `DialogueBlob` (extract them into a shared
      component first — they currently live inline).
- [ ] Export: top-level `triggers` list; each also echoed inline on its subject
      (location/item) so the agent sees it in place.

### 4b. Item logic (the real follow-through on Phase 2's "first-class items")

- [ ] Promote items to a model `Item`: `project` FK, `state_key` (the existing
      `item_*` key — keeps every dialogue requirement/effect working unchanged),
      `name`, `description`, `kind` (enum: `key` / `consumable` / `equippable` /
      `quest`), `use_effects` JSONB ("potion: `change_stat` health +25"; empty =
      not usable), `found_at` Location FK (nullable), `image_key` (same S3 pipeline,
      prefix `Items/…`). Migration backfills an `Item` row per existing `item_*`
      entry in each project's `state_schema`.
- [ ] Keep `state_schema` as the registry of *keys* (dialogue pickers unchanged);
      the `Item` row is the design detail hanging off the key. Creating an item
      registers its key; the existing auto-register path gains a "flesh this out"
      link to the item card.
- [ ] API: `GET /api/items?project_id=`, `POST`, `PATCH /{id}`, `DELETE /{id}`
      (delete only when no dialogue references the key — return 409 with the
      referencing nodes otherwise). MCP: `list_items`, `create_item`, `update_item`.
- [ ] UI: an "Items" project tab (card grid like Characters).
- [ ] Export: top-level `items` list; `found_at` also echoed on the location;
      `build_plan` orders items after the state schema, before the locations that
      contain them.

---

## 5. Aesthetic direction on entities, not just the project

**Design tradition:** the **art bible** (style guide) and **mood board** — standard
preproduction artifacts that keep every asset, made by any hand, on one visual
identity — plus the "comps/touchstones" shorthand reviewers and pitch decks use
("Hyper Light Drifter palette"). Here the "any hand" producing assets is the agent,
which makes the art bible *more* necessary, not less.

**Why:** VISION Phase 2's intent capture puts references at the project level; the
stronger lever is per-entity. Visual identity is the thing creators care most about
and currently control least — every screenshot an agent produces reflects *its* taste.

- [ ] Project-level (with VISION Phase 2 intent capture): `art_style` (free text +
      touchstones — "chunky pixel art, Hyper Light Drifter palette"), `music_mood`.
- [ ] Per-entity `style_notes` text field on `Level` and `Location` (characters
      already express this through description + portrait).
- [ ] Reference images beyond portraits: covered by 1c for locations; add the same
      upload endpoint to `Level` if level-scale art direction proves wanted — wait
      for the pull.
- [x] **Assets that actually reach the engine** (Aug 2026). Uploading art already worked;
      *using* it never did — every `image_url` is a presigned link that expires in an hour, so
      the conventions told builders to ignore art entirely. Now: a durable
      `GET /api/assets/{kind}/{id}` that streams the bytes and names the design object rather
      than the storage key, a project-wide `list_assets` MCP tool, and `sprite`
      (`cells_wide`/`cells_high`/`frames`/`fps`) so a builder knows whether a PNG is one sprite
      or a four-frame strip. Sized in **grid cells, not pixels**, so art stays tied to the
      design's unit. Greyboxing stays the first pass — assets replace it, never gate it.
- [ ] **Image generation is not on this path, on purpose.** FLUX makes illustrations;
      sprites need transparency, a fixed palette, cell-aligned dimensions and frames. Upload
      is the first-class route. Generation stays what it's good at — reference art for mood
      and characters.
- [ ] Export: project `art_direction` block + per-entity notes inline. `/kickoff`
      prompt instructs the agent: match `art_direction` before generating any asset;
      never substitute its own style where notes exist.

---

## Sequencing & dependencies

1. **VISION Phase 1 first** — none of this reaches the agent until the export/read
   layer exists. Each section above adds its objects to the export as it ships.
2. Then, by value-per-effort: **1a→1b→1c (world)** and **2a (controls)** — both cheap,
   both pure reuse of existing patterns; **2b (abilities)**; **4a/4b (triggers +
   items)** as one arc since they share the extracted requirement/effect picker;
   **3 (opposition)** when a combat-forward project needs it; **5** piecemeal
   alongside whatever entity is being touched.
3. Every new model follows the house pattern: Ninja `Schema`s in `api/api.py`,
   `npm run gen:api` after each schema change, MCP tools as thin httpx proxies with
   docstrings as the agent-facing docs, deletes validated (409 on referenced), JSONB
   for the bounded vocabularies with normalization in the frontend lib.

## Verification (per feature, same ritual)

- Model + endpoint: exercise via `/api/docs`; seed data; confirm the export carries
  the new objects and `build_plan` ordering invariants hold (keys before gated
  things, characters before encounters, items before locations that hold them).
- MCP: drive the new tools through a stdio session; confirm docstring vocabulary
  matches `frontend/src/api/client.ts` types.
- UI: create → edit → delete round-trip on the relevant page; debounced saves don't
  flood the API (watch the network tab).
- The real test, once Phase 1's Godot demo exists: does the agent's output visibly
  change when the creator changes the lever? A locked connection should gate the
  build order; a mood field should change the generated scene's dressing; an
  `inputStyle` answer should change the input map. If a lever doesn't move the
  output, it isn't a lever.
