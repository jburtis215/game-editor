/**
 * Ability params — the loose `{key: number|string|bool}` bag that tunes one player verb.
 *
 * `Ability.params` is JSONB the backend stores verbatim (same deal as `systems` and
 * `traits`), so the coercion lives here: the keys are invented per ability — a Dash has a
 * cooldown and a distance, a Grapple Hook has a range and "can swing" — and no code catalog
 * could enumerate them. Anything the API hands back that isn't a number/string/bool is
 * dropped rather than rendered as `[object Object]`.
 */
import type { Ability } from '../api/client';

export type ParamValue = number | string | boolean;
export type AbilityParams = Record<string, ParamValue>;

/** The three shapes a param can take — mirrors `TraitType`, deliberately. */
export type ParamType = 'number' | 'text' | 'toggle';

export const PARAM_TYPES: { id: ParamType; label: string }[] = [
  { id: 'number', label: 'Number' },
  { id: 'text', label: 'Text' },
  { id: 'toggle', label: 'Yes / no' },
];

/** Coerce the API's `{[key: string]: unknown}` into params we can actually render. */
export function normalizeParams(raw: Ability['params'] | undefined | null): AbilityParams {
  const params: AbilityParams = {};
  for (const [key, value] of Object.entries(raw ?? {})) {
    if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') {
      params[key] = value;
    }
  }
  return params;
}

/** Snake_case a typed label into a param key. Mirrors `traitKey()`. */
export function paramKey(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
}

/** A param key read back as a human label ("can_swing" -> "can swing"). */
export function paramLabel(key: string): string {
  return key.replace(/_/g, ' ');
}

/** The starting value for a newly added param of `type`. */
export function defaultParamValue(type: ParamType): ParamValue {
  if (type === 'number') return 0;
  if (type === 'toggle') return true;
  return '';
}
