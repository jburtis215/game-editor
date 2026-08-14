/**
 * Game-system definitions ported from the Lovable "game architect" prototype.
 *
 * This module is the single source of truth for the Settings / Systems / Preview tabs:
 * the *question definitions* live here in code, while the user's *answers* are persisted
 * on the Project (`dimension`/`genre` columns + `systems`/`hud_layout` JSONB).
 *
 * Icons are plain emoji (the app has no icon library) to stay dependency-free.
 */

// ---------- Types ----------

export type Dimension = '2d' | '3d';

export type GameType = {
  dimension: Dimension | '';
  genre: string;
};

/** Per-system enabled flag + the answers to its questions. */
export type SystemState = {
  enabled: boolean;
  values: Record<string, string | string[] | number>;
};
export type ArchitectState = Record<string, SystemState>;

export type HudPos = { x: number; y: number }; // percentages 0..100 of the stage
export type HudLayout = Record<string, HudPos>;

export type Scope = 'all' | 'player' | 'tagged';

export type OptionDef = { id: string; label: string; description?: string };

export type QuestionDef =
  | { kind: 'single'; key: string; label: string; options: OptionDef[]; defaultValue: string }
  | { kind: 'multi'; key: string; label: string; options: OptionDef[]; defaultValue: string[] }
  | {
      kind: 'slider';
      key: string;
      label: string;
      min: number;
      max: number;
      step: number;
      unit: string;
      defaultValue: number;
    };

export type SystemDef = {
  id: string;
  name: string;
  blurb: string;
  icon: string;
  components: string[];
  questions: QuestionDef[];
};

export type Genre = { id: string; name: string; blurb: string; icon: string };
export type DimensionDef = { id: Dimension; label: string; blurb: string; icon: string };

// ---------- Dimensions & genres (Settings tab) ----------

export const DIMENSIONS: DimensionDef[] = [
  { id: '2d', label: '2D', blurb: 'Side-scroll, top-down, pixel art, cards, boards', icon: '◻️' },
  { id: '3d', label: '3D', blurb: 'First/third person, world space, physics', icon: '🧊' },
];

export const GENRES: Genre[] = [
  { id: 'rpg', name: 'RPG', blurb: 'Stats, quests, party', icon: '⚔️' },
  { id: 'platformer', name: 'Platformer', blurb: 'Jump, run, precision', icon: '⛰️' },
  { id: 'shooter', name: 'Shooter', blurb: 'Aim, fire, cover', icon: '🎯' },
  { id: 'puzzle', name: 'Puzzle', blurb: 'Logic and pattern', icon: '🧩' },
  { id: 'social', name: 'Social Roleplay', blurb: 'Hangout, chat, world', icon: '👥' },
  { id: 'card', name: 'Card Game', blurb: 'Deck, hand, turns', icon: '🃏' },
  { id: 'strategy', name: 'Strategy', blurb: 'Units, map, plans', icon: '🚩' },
  { id: 'racing', name: 'Racing', blurb: 'Speed, tracks, drift', icon: '🏎️' },
  { id: 'survival', name: 'Survival', blurb: 'Gather, craft, endure', icon: '🌲' },
  { id: 'horror', name: 'Horror', blurb: 'Tension, dread, scarcity', icon: '👻' },
  { id: 'sandbox', name: 'Sandbox', blurb: 'Open systems, freeform', icon: '🔨' },
  { id: 'fighting', name: 'Fighting', blurb: '1v1, combos, frames', icon: '👑' },
  { id: 'rhythm', name: 'Rhythm', blurb: 'Beat, timing, music', icon: '🎵' },
];

// ---------- Systems (Systems tab) ----------

export const SCOPE_OPTIONS: OptionDef[] = [
  { id: 'all', label: 'All entities', description: 'Every character shares this' },
  { id: 'player', label: 'Only player', description: 'Just the playable character' },
  { id: 'tagged', label: 'Tagged group', description: 'Only specific character types' },
];

export const SYSTEMS: SystemDef[] = [
  {
    id: 'health',
    name: 'Health',
    blurb: 'Vitality, damage, and death',
    icon: '❤️',
    components: ['HealthComponent'],
    questions: [
      { kind: 'single', key: 'scope', label: 'Who has health?', options: SCOPE_OPTIONS, defaultValue: 'all' },
      {
        kind: 'single',
        key: 'regen',
        label: 'How is it restored?',
        options: [
          { id: 'auto', label: 'Auto-regeneration', description: 'Heals over time when out of combat' },
          { id: 'pickup', label: 'Consumable pickups', description: 'Player must collect items' },
          { id: 'rest', label: 'Rest / save points', description: 'Restored at specific locations' },
          { id: 'never', label: 'Never', description: 'Damage is permanent until death' },
        ],
        defaultValue: 'auto',
      },
      {
        kind: 'single',
        key: 'display',
        label: 'Visual representation',
        options: [
          { id: 'bar', label: 'Bar' },
          { id: 'hearts', label: 'Hearts' },
          { id: 'numeric', label: 'Numeric' },
          { id: 'hidden', label: 'Hidden' },
        ],
        defaultValue: 'hearts',
      },
      { kind: 'slider', key: 'lethality', label: 'Lethality threshold', min: 0, max: 100, step: 5, unit: '% HP', defaultValue: 65 },
    ],
  },
  {
    id: 'stamina',
    name: 'Stamina',
    blurb: 'Sprint, jump, and exertion',
    icon: '👟',
    components: ['StaminaComponent'],
    questions: [
      { kind: 'single', key: 'scope', label: 'Who has stamina?', options: SCOPE_OPTIONS, defaultValue: 'all' },
      {
        kind: 'multi',
        key: 'drains',
        label: 'What drains stamina?',
        options: [
          { id: 'sprint', label: 'Sprinting' },
          { id: 'jump', label: 'Jumping' },
          { id: 'attack', label: 'Attacking' },
          { id: 'block', label: 'Blocking' },
        ],
        defaultValue: ['sprint', 'jump'],
      },
      { kind: 'slider', key: 'regenRate', label: 'Regen rate', min: 1, max: 50, step: 1, unit: '/sec', defaultValue: 12 },
    ],
  },
  {
    id: 'movement',
    name: 'Movement',
    blurb: 'Running, jumping, and gravity',
    icon: '🏃',
    // BASE_COMPONENTS already provides MovementController on every character;
    // these are the tunable additions this system layers on top.
    components: ['JumpComponent', 'LocomotionTuning'],
    questions: [
      { kind: 'single', key: 'scope', label: 'Who moves like this?', options: SCOPE_OPTIONS, defaultValue: 'all' },
      { kind: 'slider', key: 'jumpHeight', label: 'Jump height', min: 1, max: 10, step: 1, unit: 'units', defaultValue: 3 },
      { kind: 'slider', key: 'gravity', label: 'Gravity', min: 10, max: 200, step: 5, unit: '% of Earth', defaultValue: 100 },
      { kind: 'slider', key: 'runSpeed', label: 'Run speed', min: 1, max: 20, step: 1, unit: 'units/sec', defaultValue: 8 },
    ],
  },
  {
    id: 'magic',
    name: 'Magic / Mana',
    blurb: 'Spells, mana, and cooldowns',
    icon: '✨',
    components: ['ManaPool', 'SpellCaster'],
    questions: [
      { kind: 'single', key: 'scope', label: 'Who can cast?', options: SCOPE_OPTIONS, defaultValue: 'tagged' },
      {
        kind: 'single',
        key: 'resource',
        label: 'Resource model',
        options: [
          { id: 'mana', label: 'Mana pool', description: 'Spend from a refillable pool' },
          { id: 'cooldown', label: 'Cooldowns', description: 'Each spell on its own timer' },
          { id: 'charges', label: 'Charges', description: 'Limited uses per encounter' },
        ],
        defaultValue: 'mana',
      },
      {
        kind: 'multi',
        key: 'schools',
        label: 'Spell schools',
        options: [
          { id: 'fire', label: 'Fire' },
          { id: 'frost', label: 'Frost' },
          { id: 'nature', label: 'Nature' },
          { id: 'arcane', label: 'Arcane' },
          { id: 'shadow', label: 'Shadow' },
        ],
        defaultValue: ['fire', 'frost'],
      },
    ],
  },
  {
    id: 'inventory',
    name: 'Inventory',
    blurb: 'Items, slots, and weight',
    icon: '🎒',
    components: ['InventoryController'],
    questions: [
      { kind: 'single', key: 'scope', label: 'Who carries an inventory?', options: SCOPE_OPTIONS, defaultValue: 'player' },
      {
        kind: 'single',
        key: 'capacity',
        label: 'Capacity model',
        options: [
          { id: 'slots', label: 'Slot-based' },
          { id: 'weight', label: 'Weight-based' },
          { id: 'unlimited', label: 'Unlimited' },
        ],
        defaultValue: 'slots',
      },
      { kind: 'slider', key: 'slots', label: 'Default slots', min: 4, max: 64, step: 1, unit: 'slots', defaultValue: 12 },
    ],
  },
  {
    id: 'combat',
    name: 'Combat',
    blurb: 'How damage is dealt',
    icon: '🗡️',
    components: ['CombatComponent'],
    questions: [
      { kind: 'single', key: 'scope', label: 'Who can fight?', options: SCOPE_OPTIONS, defaultValue: 'all' },
      {
        kind: 'multi',
        key: 'modes',
        label: 'Combat modes',
        options: [
          { id: 'melee', label: 'Melee' },
          { id: 'ranged', label: 'Ranged' },
          { id: 'magic', label: 'Magical' },
        ],
        defaultValue: ['melee'],
      },
    ],
  },
  {
    id: 'dialogue',
    name: 'Dialogue',
    blurb: 'Conversations and choices',
    icon: '💬',
    components: ['DialogueController'],
    questions: [
      { kind: 'single', key: 'scope', label: 'Who speaks?', options: SCOPE_OPTIONS, defaultValue: 'tagged' },
      {
        kind: 'single',
        key: 'branching',
        label: 'Branching',
        options: [
          { id: 'linear', label: 'Linear', description: 'One line at a time' },
          { id: 'choice', label: 'Player choice', description: 'Player picks responses' },
          { id: 'tree', label: 'Full dialogue tree', description: 'Conditional, stateful branches' },
        ],
        defaultValue: 'choice',
      },
    ],
  },
  {
    id: 'controls',
    name: 'Controls & Camera',
    blurb: 'How the player drives, and what they see',
    icon: '🎮',
    components: ['InputController', 'CameraRig'],
    questions: [
      {
        kind: 'single',
        key: 'inputStyle',
        label: 'How does the player control the game?',
        options: [
          { id: 'platformer', label: 'Platformer', description: 'Left/right + jump, gravity-bound' },
          { id: 'twin-stick', label: 'Twin-stick', description: 'Move and aim independently' },
          { id: 'point-and-click', label: 'Point and click', description: 'Cursor drives everything' },
          { id: 'wasd-mouse', label: 'WASD + mouse', description: 'Keyboard moves, mouse aims/looks' },
        ],
        defaultValue: 'wasd-mouse',
      },
      {
        kind: 'single',
        key: 'camera',
        label: 'Where is the camera?',
        options: [
          { id: 'side-on', label: 'Side-on', description: 'Flat side view, scrolls with the player' },
          { id: 'top-down', label: 'Top-down', description: 'Looking down on the play space' },
          { id: 'third-person', label: 'Follow third-person', description: 'Trails behind the character' },
          { id: 'fixed-rooms', label: 'Fixed rooms', description: 'One framed shot per room, no scrolling' },
        ],
        defaultValue: 'side-on',
      },
      { kind: 'slider', key: 'cameraFeel', label: 'Camera feel (locked → loose follow)', min: 0, max: 100, step: 5, unit: '% loose', defaultValue: 40 },
    ],
  },
];

/** Always-present components on every character (shown as the "foundation" base). */
export const BASE_COMPONENTS = [
  { name: 'TransformComponent', note: 'Position, rotation, scale' },
  { name: 'MovementController', note: 'Walk, jump, physics' },
];

/** HUD labels + default positions for the Preview tab. */
export const SYSTEM_LABELS: Record<string, string> = {
  health: 'Health',
  magic: 'Magic',
  stamina: 'Stamina',
  inventory: 'Inventory',
  combat: 'Weapon',
  dialogue: 'Dialogue',
};

export const DEFAULT_HUD_LAYOUT: HudLayout = {
  health: { x: 3, y: 4 },
  magic: { x: 3, y: 22 },
  stamina: { x: 3, y: 40 },
  inventory: { x: 75, y: 4 },
  combat: { x: 3, y: 82 },
  dialogue: { x: 25, y: 80 },
};

// ---------- Helpers ----------

function defaultValues(sys: SystemDef): Record<string, string | string[] | number> {
  const out: Record<string, string | string[] | number> = {};
  for (const q of sys.questions) out[q.key] = q.defaultValue;
  return out;
}

/** Every system present, with default answers; a small set enabled by default. */
export function initialState(): ArchitectState {
  const out: ArchitectState = {};
  for (const s of SYSTEMS) {
    out[s.id] = {
      enabled: ['health', 'inventory', 'stamina', 'controls'].includes(s.id),
      values: defaultValues(s),
    };
  }
  return out;
}

/**
 * Per-genre answers for the Controls & Camera system — the 3Cs vary more by genre than
 * any other system, so a genre pick should seed them rather than leave a generic default.
 */
const CONTROL_DEFAULTS: Record<string, { inputStyle: string; camera: string; cameraFeel: number }> = {
  rpg: { inputStyle: 'wasd-mouse', camera: 'top-down', cameraFeel: 55 },
  platformer: { inputStyle: 'platformer', camera: 'side-on', cameraFeel: 35 },
  shooter: { inputStyle: 'twin-stick', camera: 'top-down', cameraFeel: 45 },
  puzzle: { inputStyle: 'point-and-click', camera: 'fixed-rooms', cameraFeel: 0 },
  social: { inputStyle: 'wasd-mouse', camera: 'third-person', cameraFeel: 65 },
  card: { inputStyle: 'point-and-click', camera: 'fixed-rooms', cameraFeel: 0 },
  strategy: { inputStyle: 'point-and-click', camera: 'top-down', cameraFeel: 25 },
  racing: { inputStyle: 'wasd-mouse', camera: 'third-person', cameraFeel: 80 },
  survival: { inputStyle: 'wasd-mouse', camera: 'third-person', cameraFeel: 60 },
  horror: { inputStyle: 'wasd-mouse', camera: 'fixed-rooms', cameraFeel: 15 },
  sandbox: { inputStyle: 'wasd-mouse', camera: 'third-person', cameraFeel: 70 },
  fighting: { inputStyle: 'platformer', camera: 'side-on', cameraFeel: 10 },
  rhythm: { inputStyle: 'point-and-click', camera: 'fixed-rooms', cameraFeel: 0 },
};

/** Initial state tuned to a genre (which systems start enabled + their genre-specific answers). */
export function genreDefaults(genre: string): ArchitectState {
  const base = initialState();
  const enable = (ids: string[]) => {
    // Controls & Camera is the 3Cs foundation — every genre needs it, so it stays on.
    for (const id of Object.keys(base)) base[id].enabled = id === 'controls' || ids.includes(id);
  };
  switch (genre) {
    case 'rpg': enable(['health', 'stamina', 'movement', 'magic', 'inventory', 'combat', 'dialogue']); break;
    case 'shooter': enable(['health', 'stamina', 'movement', 'inventory', 'combat']); break;
    case 'platformer': enable(['health', 'stamina', 'movement']); break;
    case 'puzzle': enable(['inventory']); break;
    case 'card': enable(['health', 'magic']); break;
    case 'social': enable(['inventory', 'dialogue']); break;
    case 'survival': enable(['health', 'stamina', 'movement', 'inventory', 'combat']); break;
    case 'racing': enable(['stamina', 'movement']); break;
    case 'strategy': enable(['combat', 'inventory']); break;
    case 'horror': enable(['health', 'stamina', 'movement', 'inventory']); break;
    case 'sandbox': enable(['health', 'stamina', 'movement', 'inventory', 'combat']); break;
    case 'fighting': enable(['health', 'stamina', 'movement', 'combat']); break;
  }
  const controls = CONTROL_DEFAULTS[genre];
  if (controls) base.controls.values = { ...base.controls.values, ...controls };
  return base;
}

/**
 * Coerce the loosely-typed `systems` JSON from the API into a complete ArchitectState,
 * filling any missing systems/answers with defaults so the UI is always well-formed.
 */
export function normalizeSystems(raw: unknown): ArchitectState {
  const base = initialState();
  if (raw && typeof raw === 'object') {
    const data = raw as Record<string, Partial<SystemState>>;
    for (const id of Object.keys(base)) {
      const incoming = data[id];
      if (!incoming) continue;
      base[id] = {
        enabled: typeof incoming.enabled === 'boolean' ? incoming.enabled : base[id].enabled,
        values: { ...base[id].values, ...(incoming.values ?? {}) },
      };
    }
  }
  return base;
}

/** Coerce the `hud_layout` JSON into a complete HudLayout (defaults for missing entries). */
export function normalizeHudLayout(raw: unknown): HudLayout {
  const out: HudLayout = { ...DEFAULT_HUD_LAYOUT };
  if (raw && typeof raw === 'object') {
    const data = raw as Record<string, Partial<HudPos>>;
    for (const id of Object.keys(out)) {
      const p = data[id];
      if (p && typeof p.x === 'number' && typeof p.y === 'number') out[id] = { x: p.x, y: p.y };
    }
  }
  return out;
}

/** Build the "ai-game-maker" blueprint manifest from the current state. */
export function buildManifest(gameType: GameType, state: ArchitectState) {
  const foundation: SystemDef[] = [];
  const extensions: { sys: SystemDef; scopeNote: string }[] = [];
  for (const sys of SYSTEMS) {
    const st = state[sys.id];
    if (!st?.enabled) continue;
    const scope = (st.values['scope'] as Scope) ?? 'all';
    if (scope === 'all') foundation.push(sys);
    else extensions.push({ sys, scopeNote: scope === 'player' ? 'Player only' : 'Tagged characters' });
  }
  return {
    target: 'ai-game-maker',
    game: { dimension: gameType.dimension || null, genre: gameType.genre || null },
    baseClass: 'BaseCharacter',
    foundation: [...BASE_COMPONENTS.map((b) => b.name), ...foundation.flatMap((f) => f.components)],
    extensions: extensions.map((e) => ({
      name: `${e.sys.name}Extension`,
      appliesTo: e.scopeNote,
      components: e.sys.components,
      config: state[e.sys.id].values,
    })),
    foundationConfig: Object.fromEntries(foundation.map((f) => [f.id, state[f.id].values])),
  };
}
