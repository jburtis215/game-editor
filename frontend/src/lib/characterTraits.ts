/**
 * Character traits — the catalog, the persisted shapes, and the overlay resolver.
 *
 * A trait is a named, typed slot on a character: `number` (Power = 75), `text` (Species = "Elf")
 * or `toggle` (Can fly = ✓).
 *
 * Two places store traits:
 *   - `Project.character_traits` — a list of trait *definitions* every character in the project
 *     shows (chosen in the Settings tab).
 *   - `Character.traits` — `{ values, own }`: `values` holds this character's value for any trait
 *     (a project default it overrides, or one of its own), `own` holds definitions for traits only
 *     this character has.
 *
 * Unlike `gameSystems.ts` — where the question set is fixed in code and only answers persist —
 * a trait's *full definition* is persisted, because traits can be custom and no code catalog could
 * describe them. `TRAIT_CATALOG` below is therefore only a picker source: editing it never
 * invalidates saved data.
 *
 * The project's defaults are overlaid live at render time (`resolveTraits`), so removing a default
 * in Settings removes it from every character immediately — no backfill, no sync step.
 */

// ---------- Types ----------

export type TraitType = 'number' | 'text' | 'toggle';
export type TraitValue = number | string | boolean;

export type TraitDef = {
  key: string;
  label: string;
  type: TraitType;
  /** Numbers only. */
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  default: TraitValue;
  /** Catalog grouping — absent on custom traits. */
  category?: string;
};

/** The `Character.traits` JSONB shape. */
export type CharacterTraits = {
  values: Record<string, TraitValue>;
  own: TraitDef[];
};

/** A trait as displayed on a character: its definition, its effective value, and where it came from. */
export type ResolvedTrait = {
  def: TraitDef;
  value: TraitValue;
  source: 'project' | 'own';
  /** True when the character stores its own value rather than falling back to `def.default`. */
  overridden: boolean;
};

export const TRAIT_TYPES: { id: TraitType; label: string }[] = [
  { id: 'number', label: 'Number' },
  { id: 'text', label: 'Text' },
  { id: 'toggle', label: 'Yes / no' },
];

// ---------- Catalog ----------

export const TRAIT_CATEGORIES = [
  { id: 'combat', label: 'Combat', icon: '⚔️' },
  { id: 'physical', label: 'Physical', icon: '🏃' },
  { id: 'mental', label: 'Mental', icon: '🧠' },
  { id: 'social', label: 'Social', icon: '💬' },
  { id: 'progression', label: 'Progression', icon: '📈' },
  { id: 'identity', label: 'Identity', icon: '🪪' },
  { id: 'flags', label: 'Flags', icon: '🚩' },
] as const;

/** A 0–100 stat — the shape most combat/mental/social traits take. */
function stat(category: string, key: string, label: string, defaultValue = 50): TraitDef {
  return { key, label, type: 'number', min: 0, max: 100, step: 1, unit: '', default: defaultValue, category };
}

function num(
  category: string,
  key: string,
  label: string,
  min: number,
  max: number,
  step: number,
  unit: string,
  defaultValue: number,
): TraitDef {
  return { key, label, type: 'number', min, max, step, unit, default: defaultValue, category };
}

function text(category: string, key: string, label: string): TraitDef {
  return { key, label, type: 'text', default: '', category };
}

function flag(key: string, label: string, defaultValue = false): TraitDef {
  return { key, label, type: 'toggle', default: defaultValue, category: 'flags' };
}

export const TRAIT_CATALOG: TraitDef[] = [
  // Combat
  stat('combat', 'power', 'Power'),
  stat('combat', 'attack', 'Attack'),
  stat('combat', 'defense', 'Defense'),
  stat('combat', 'health', 'Health', 100),
  stat('combat', 'magic', 'Magic'),
  stat('combat', 'mana', 'Mana'),
  stat('combat', 'speed', 'Speed'),
  stat('combat', 'accuracy', 'Accuracy', 75),
  stat('combat', 'evasion', 'Evasion', 25),
  num('combat', 'crit_chance', 'Critical chance', 0, 100, 1, '%', 5),
  stat('combat', 'armor', 'Armor', 25),
  num('combat', 'range', 'Range', 0, 100, 1, 'm', 5),

  // Physical
  stat('physical', 'strength', 'Strength'),
  stat('physical', 'agility', 'Agility'),
  stat('physical', 'endurance', 'Endurance'),
  num('physical', 'height', 'Height', 0, 300, 1, 'cm', 175),
  num('physical', 'weight', 'Weight', 0, 500, 1, 'kg', 70),
  num('physical', 'age', 'Age', 0, 1000, 1, 'yrs', 25),
  text('physical', 'build', 'Build'),
  text('physical', 'eye_color', 'Eye color'),
  text('physical', 'hair_color', 'Hair color'),

  // Mental
  stat('mental', 'intelligence', 'Intelligence'),
  stat('mental', 'wisdom', 'Wisdom'),
  stat('mental', 'perception', 'Perception'),
  stat('mental', 'willpower', 'Willpower'),
  stat('mental', 'sanity', 'Sanity', 100),
  stat('mental', 'courage', 'Courage'),
  stat('mental', 'focus', 'Focus'),
  stat('mental', 'curiosity', 'Curiosity'),

  // Social
  stat('social', 'charisma', 'Charisma'),
  stat('social', 'charm', 'Charm'),
  stat('social', 'reputation', 'Reputation'),
  stat('social', 'loyalty', 'Loyalty'),
  stat('social', 'empathy', 'Empathy'),
  stat('social', 'deception', 'Deception'),
  stat('social', 'intimidation', 'Intimidation'),
  stat('social', 'persuasion', 'Persuasion'),

  // Progression
  num('progression', 'level', 'Level', 1, 99, 1, '', 1),
  num('progression', 'experience', 'Experience', 0, 999999, 100, 'xp', 0),
  num('progression', 'skill_points', 'Skill points', 0, 999, 1, '', 0),
  num('progression', 'gold', 'Gold', 0, 999999, 10, 'g', 0),
  num('progression', 'inventory_slots', 'Inventory slots', 0, 200, 1, '', 20),
  num('progression', 'carry_capacity', 'Carry capacity', 0, 1000, 5, 'kg', 50),

  // Identity
  text('identity', 'species', 'Species'),
  text('identity', 'class', 'Class'),
  text('identity', 'occupation', 'Occupation'),
  text('identity', 'faction', 'Faction'),
  text('identity', 'alignment', 'Alignment'),
  text('identity', 'home_region', 'Home region'),
  text('identity', 'voice', 'Voice'),
  text('identity', 'pronouns', 'Pronouns'),

  // Flags
  flag('playable', 'Playable'),
  flag('hostile', 'Hostile'),
  flag('immortal', 'Immortal'),
  flag('can_fly', 'Can fly'),
  flag('can_swim', 'Can swim'),
  flag('merchant', 'Merchant'),
  flag('quest_giver', 'Quest giver'),
];

// ---------- Helpers ----------

/** Slugify a label into a stable snake_case key. Mirrors `_slug()` in the MCP server. */
export function traitKey(label: string): string {
  return (
    label
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'trait'
  );
}

/** The zero value for a trait type — what a definition falls back to when `default` is missing. */
function fallbackDefault(type: TraitType): TraitValue {
  return type === 'number' ? 0 : type === 'toggle' ? false : '';
}

/** Coerce a loose value into one valid for `def` (clamping numbers into [min, max]). */
export function coerceValue(def: TraitDef, raw: unknown): TraitValue {
  if (def.type === 'number') {
    const n = typeof raw === 'number' ? raw : Number(raw);
    if (!Number.isFinite(n)) return typeof def.default === 'number' ? def.default : 0;
    const min = def.min ?? Number.NEGATIVE_INFINITY;
    const max = def.max ?? Number.POSITIVE_INFINITY;
    return Math.min(max, Math.max(min, n));
  }
  if (def.type === 'toggle') return Boolean(raw);
  return typeof raw === 'string' ? raw : String(raw ?? '');
}

/** Coerce one loose JSON entry into a well-formed `TraitDef`, or null if it's unusable. */
function normalizeTraitDef(raw: unknown): TraitDef | null {
  if (!raw || typeof raw !== 'object') return null;
  const d = raw as Record<string, unknown>;
  const key = typeof d.key === 'string' ? d.key.trim() : '';
  if (!key) return null;
  const type: TraitType =
    d.type === 'number' || d.type === 'text' || d.type === 'toggle' ? d.type : 'number';
  const def: TraitDef = {
    key,
    label: typeof d.label === 'string' && d.label ? d.label : key,
    type,
    default: fallbackDefault(type),
    ...(typeof d.category === 'string' ? { category: d.category } : {}),
  };
  if (type === 'number') {
    def.min = typeof d.min === 'number' ? d.min : 0;
    def.max = typeof d.max === 'number' ? d.max : 100;
    if (def.max < def.min) def.max = def.min;
    def.step = typeof d.step === 'number' && d.step > 0 ? d.step : 1;
    def.unit = typeof d.unit === 'string' ? d.unit : '';
  }
  def.default = coerceValue(def, d.default ?? fallbackDefault(type));
  return def;
}

/** Coerce `Project.character_traits` into a well-formed, key-unique list of definitions. */
export function normalizeTraitDefs(raw: unknown): TraitDef[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const out: TraitDef[] = [];
  for (const entry of raw) {
    const def = normalizeTraitDef(entry);
    if (!def || seen.has(def.key)) continue;
    seen.add(def.key);
    out.push(def);
  }
  return out;
}

/** Coerce `Character.traits` into a well-formed `{ values, own }`. */
export function normalizeCharacterTraits(raw: unknown): CharacterTraits {
  const empty: CharacterTraits = { values: {}, own: [] };
  if (!raw || typeof raw !== 'object') return empty;
  const data = raw as Record<string, unknown>;
  const own = normalizeTraitDefs(data.own);
  const values: Record<string, TraitValue> = {};
  if (data.values && typeof data.values === 'object') {
    for (const [key, value] of Object.entries(data.values as Record<string, unknown>)) {
      if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') {
        values[key] = value;
      }
    }
  }
  return { values, own };
}

/**
 * The character's effective trait list: the project's defaults first, then the character's own.
 * A project default wins any key collision, so a character can never shadow the project's
 * definition of a trait — only its value.
 */
export function resolveTraits(defs: TraitDef[], traits: CharacterTraits): ResolvedTrait[] {
  const out: ResolvedTrait[] = [];
  const seen = new Set<string>();
  const push = (def: TraitDef, source: 'project' | 'own') => {
    if (seen.has(def.key)) return;
    seen.add(def.key);
    const stored = traits.values[def.key];
    const overridden = stored !== undefined;
    out.push({ def, value: overridden ? coerceValue(def, stored) : def.default, source, overridden });
  };
  for (const def of defs) push(def, 'project');
  for (const def of traits.own) push(def, 'own');
  return out;
}

/** Format a value for read-only display (a summary line, a badge). */
export function formatTraitValue(def: TraitDef, value: TraitValue): string {
  if (def.type === 'toggle') return value ? 'Yes' : 'No';
  if (def.type === 'number') return def.unit ? `${value} ${def.unit}` : String(value);
  return String(value) || '—';
}
