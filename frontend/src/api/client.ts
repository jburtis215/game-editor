import createClient from 'openapi-fetch';
import type { components, paths } from './schema';

/**
 * Typed API client generated from the Django Ninja OpenAPI schema.
 * Regenerate the schema with `npm run gen:api` (backend must be running).
 */
/** Base URL of the backend API — also used for direct `fetch` calls (e.g. multipart uploads). */
export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const api = createClient<paths>({ baseUrl: API_BASE });

// Re-export the backend's schemas as usable TS objects.
export type Character = components['schemas']['CharacterOut'];
export type CharacterDetail = components['schemas']['CharacterDetailOut'];
export type RelatedCharacter = components['schemas']['RelatedCharacterOut'];
export type LevelCharacter = components['schemas']['LevelCharacterOut'];
export type Project = components['schemas']['ProjectOut'];
export type Level = components['schemas']['LevelOut'];
export type Location = components['schemas']['LocationOut'];
/** An exit out of a location, described relative to the location it's listed on. */
export type LocationConnection = components['schemas']['LocationConnectionOut'];
/** One verb in the player's vocabulary — what the player can do (Dash, Double Jump). */
export type Ability = components['schemas']['AbilityOut'];
export type Scene = components['schemas']['SceneOut'];
export type DialogueSummary = components['schemas']['DialogueSummaryOut'];
export type DialogueDetail = components['schemas']['DialogueDetailOut'];
export type DialogueNode = components['schemas']['DialogueNodeOut'];
export type DialogueParent = components['schemas']['DialogueParentOut'];

export type User = components['schemas']['UserOut'];

export type StateEntryType = 'remembered_choice' | 'item' | 'stat' | 'flag';

export type StateEntry = {
  id: string;
  label: string;
  type: StateEntryType;
  source_dialogue_id?: number;
};

export type StateSchema = Record<string, StateEntry>;

/**
 * A gate in the bounded requirement vocabulary. Used by dialogue responses
 * (`Dialogue.requirements`) and by location connections (`LocationConnection.requirements`
 * — "locked until item_cellar_key"); the backend and the MCP docstrings share it verbatim.
 */
export type DialogueRequirement =
  | {
      type: 'state_equals';
      state_key: string;
      value: boolean | string | number;
    }
  | {
      type: 'stat_check';
      state_key: string;
      op: 'at_least' | 'less_than' | 'equals';
      value: number;
    }
  | {
      type: 'has_item';
      state_key: string;
    };

export type DialogueEffect =
  | {
      type: 'remember_choice';
      state_key: string;
      label: string;
    }
  | {
      type: 'give_item';
      state_key: string;
      label: string;
    }
  | {
      type: 'remove_item';
      state_key: string;
    }
  | {
      type: 'change_stat';
      state_key: string;
      label: string;
      amount: number;
    }
  | {
      type: 'set_flag';
      state_key: string;
      label: string;
      value: boolean;
    };

// Available UI themes (must match the backend User.THEME_CHOICES).
export const THEMES = ['neon', 'aqua', 'light', 'studio'] as const;
export type Theme = (typeof THEMES)[number];
