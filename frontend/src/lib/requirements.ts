/**
 * Helpers for the bounded *requirement* vocabulary (`has_item` / `stat_check` /
 * `state_equals` / `remembered_choice`).
 *
 * Requirements gate more than dialogue: a `LocationConnection` uses the same shape to lock
 * an exit ("locked until item_cellar_key"). These two helpers are what every picker needs —
 * the state a requirement may reference, and how to read one back in plain English — so they
 * live here rather than inside one component.
 */
import type { DialogueRequirement, StateEntry, StateSchema } from '../api/client';

/** The state entries a requirement of this type may reference (what `MemoryComboBox` lists). */
export function getStateEntriesByType(stateSchema: StateSchema, type: StateEntry['type']) {
  return Object.values(stateSchema).filter((entry) => entry.type === type);
}

/** The state type a requirement picker of `kind` should search. */
export function stateTypeForRequirement(
  kind: 'remembered_choice' | 'has_item' | 'stat_check' | 'flag',
): StateEntry['type'] {
  if (kind === 'has_item') return 'item';
  if (kind === 'stat_check') return 'stat';
  if (kind === 'remembered_choice') return 'remembered_choice';
  return 'flag';
}

/** Plain-English rendering of a requirement, using the state schema for human labels. */
export function getRequirementLabel(requirement: DialogueRequirement, stateSchema: StateSchema) {
  const entry = stateSchema[requirement.state_key];
  const label = entry?.label ?? requirement.state_key;

  if (requirement.type === 'has_item') return `Requires item: ${label}`;

  if (requirement.type === 'stat_check') {
    const opLabel =
      requirement.op === 'at_least'
        ? 'at least'
        : requirement.op === 'less_than'
          ? 'less than'
          : 'equal to';
    return `Requires stat: ${label} ${opLabel} ${requirement.value}`;
  }

  if (entry?.type === 'remembered_choice') return `Requires choice: ${label}`;
  return `Requires: ${label} = ${requirement.value === true ? 'Yes' : String(requirement.value)}`;
}
