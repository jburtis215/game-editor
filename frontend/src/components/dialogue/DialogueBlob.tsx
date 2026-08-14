import { useState } from 'react';
import type {
  Character,
  DialogueDetail,
  DialogueEffect,
  DialogueRequirement,
  StateEntry,
  StateSchema,
} from '../../api/client';
import {
  getRequirementLabel,
  getStateEntriesByType,
  stateTypeForRequirement,
} from '../../lib/requirements';
import { DialogueForm } from './DialogueForm';
import { MemoryComboBox } from './MemoryComboBox';


function slugify(label: string) {
  return label
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function makeUniqueStateKey(baseKey: string, stateSchema: StateSchema) {
  if (!stateSchema[baseKey]) return baseKey;
  let index = 2;
  let candidate = `${baseKey}_${index}`;
  while (stateSchema[candidate]) {
    index += 1;
    candidate = `${baseKey}_${index}`;
  }
  return candidate;
}

function getEffectLabel(effect: DialogueEffect) {
  if (effect.type === 'remember_choice') return `Remember choice: ${effect.label}`;
  if (effect.type === 'give_item') return `Give item: ${effect.label}`;
  if (effect.type === 'remove_item') return 'Remove item';
  if (effect.type === 'change_stat') {
    const sign = effect.amount > 0 ? '+' : '';
    return `Change stat: ${effect.label} ${sign}${effect.amount}`;
  }
  if (effect.type === 'set_flag') return `Set flag: ${effect.label} = ${effect.value ? 'Yes' : 'No'}`;
  return 'Effect';
}

interface DialogueBlobProps {
  detail: DialogueDetail;
  characters: Character[];
  stateSchema: StateSchema;
  onSave: (
    text: string,
    characterId: number | null,
    requirements?: DialogueRequirement[],
    effects?: DialogueEffect[],
    nextStateSchema?: StateSchema,
  ) => void;
  onCreateCharacter?: (name: string) => Promise<Character | null>;
}

/**
 * The current dialogue, emphasized in the center of the stage. Shows a character
 * portrait placeholder, the speaker name, the dialogue text, and a metadata panel
 * (placeholders to be filled in later). The "Edit" button swaps the body for a form.
 */
export function DialogueBlob({
  detail,
  characters,
  stateSchema,
  onSave,
  onCreateCharacter,
}: DialogueBlobProps) {
  const [editing, setEditing] = useState(false);

  const [draftEffects, setDraftEffects] = useState<DialogueEffect[]>(
    (detail.effects ?? []) as DialogueEffect[],
  );
  const [draftRequirements, setDraftRequirements] = useState<DialogueRequirement[]>(
    (detail.requirements ?? []) as DialogueRequirement[],
  );
  const [requirementType, setRequirementType] = useState<
    'remembered_choice' | 'has_item' | 'stat_check' | 'flag'
  >('remembered_choice');
  const [requirementStateKey, setRequirementStateKey] = useState('');
  const [requirementStatOp, setRequirementStatOp] = useState<'at_least' | 'less_than' | 'equals'>(
    'at_least',
  );
  const [requirementValue, setRequirementValue] = useState(1);
  const [requirementFlagValue, setRequirementFlagValue] = useState(true);
  const [effectType, setEffectType] = useState<DialogueEffect['type']>('remember_choice');
  const [effectLabel, setEffectLabel] = useState('');
  const [effectAmount, setEffectAmount] = useState(1);
  const [effectFlagValue, setEffectFlagValue] = useState(true);

  function addRequirement() {
    if (!requirementStateKey) return;

    let nextRequirement: DialogueRequirement;
    if (requirementType === 'has_item') {
      nextRequirement = { type: 'has_item', state_key: requirementStateKey };
    } else if (requirementType === 'stat_check') {
      nextRequirement = {
        type: 'stat_check',
        state_key: requirementStateKey,
        op: requirementStatOp,
        value: requirementValue,
      };
    } else {
      nextRequirement = {
        type: 'state_equals',
        state_key: requirementStateKey,
        value: requirementFlagValue,
      };
    }

    const nextRequirements = [...draftRequirements, nextRequirement];
    setDraftRequirements(nextRequirements);
    setRequirementStateKey('');
    onSave(detail.text, detail.character?.id ?? null, nextRequirements, draftEffects);
  }

  function removeRequirement(indexToRemove: number) {
    const nextRequirements = draftRequirements.filter((_, index) => index !== indexToRemove);
    setDraftRequirements(nextRequirements);
    onSave(detail.text, detail.character?.id ?? null, nextRequirements, draftEffects);
  }

  function addEffect() {
    const label = effectLabel.trim();
    if (!label) return;

    let stateType: StateEntry['type'] = 'flag';
    let prefix = 'flag';
    if (effectType === 'remember_choice') {
      stateType = 'remembered_choice';
      prefix = 'choice';
    } else if (effectType === 'give_item' || effectType === 'remove_item') {
      stateType = 'item';
      prefix = 'item';
    } else if (effectType === 'change_stat') {
      stateType = 'stat';
      prefix = 'stat';
    }

    const stateKey = makeUniqueStateKey(`${prefix}_${slugify(label)}`, stateSchema);
    const nextStateSchema: StateSchema = {
      ...stateSchema,
      [stateKey]: {
        id: stateKey,
        label,
        type: stateType,
        source_dialogue_id: detail.id,
      },
    };

    let nextEffect: DialogueEffect;
    if (effectType === 'remember_choice') {
      nextEffect = { type: 'remember_choice', state_key: stateKey, label };
    } else if (effectType === 'give_item') {
      nextEffect = { type: 'give_item', state_key: stateKey, label };
    } else if (effectType === 'remove_item') {
      nextEffect = { type: 'remove_item', state_key: stateKey };
    } else if (effectType === 'change_stat') {
      nextEffect = { type: 'change_stat', state_key: stateKey, label, amount: effectAmount };
    } else {
      nextEffect = { type: 'set_flag', state_key: stateKey, label, value: effectFlagValue };
    }

    setDraftEffects((current) => [...current, nextEffect]);
    setEffectLabel('');
    onSave(
      detail.text,
      detail.character?.id ?? null,
      draftRequirements,
      [...draftEffects, nextEffect],
      nextStateSchema,
    );
  }

  function removeEffect(indexToRemove: number) {
    const nextEffects = draftEffects.filter((_, index) => index !== indexToRemove);
    setDraftEffects(nextEffects);
    onSave(
      detail.text,
      detail.character?.id ?? null,
      draftRequirements,
      nextEffects,
    );
  }

  return (
    <article className="dialogue-blob">
      {!editing && (
        <button
          type="button"
          className="dialogue-blob__edit"
          onClick={() => setEditing(true)}
        >
          Edit
        </button>
      )}

      <div className="dialogue-blob__portrait" aria-hidden>
        {detail.character?.image_url ? (
          <img className="dialogue-blob__portrait-img" src={detail.character.image_url} alt="" />
        ) : (
          <span className="dialogue-blob__portrait-text">
            {detail.character?.name?.[0] ?? '?'}
          </span>
        )}
      </div>

      <div className="dialogue-blob__body">
        {editing ? (
          <>
            <DialogueForm
              characters={characters}
              initialText={detail.text}
              initialCharacterId={detail.character?.id ?? null}
              submitLabel="Save"
              onSubmit={(text, characterId) => {
                onSave(
                  text,
                  characterId,
                  draftRequirements,
                  draftEffects,
                );
                setEditing(false);
              }}
              onCancel={() => setEditing(false)}
              onCreateCharacter={onCreateCharacter}
            />
            <div className="dialogue-requirements">
              <div className="dialogue-effects__header">Only show this choice if...</div>
              <div className="dialogue-effects__row">
                <select
                  className="dialogue-effects__select"
                  value={requirementType}
                  onChange={(event) => {
                    setRequirementType(
                      event.target.value as 'remembered_choice' | 'has_item' | 'stat_check' | 'flag',
                    );
                    setRequirementStateKey('');
                  }}
                >
                  <option value="remembered_choice">Player previously chose</option>
                  <option value="has_item">Player has item</option>
                  <option value="stat_check">Stat check</option>
                  <option value="flag">Flag is</option>
                </select>

                <MemoryComboBox
                  entries={getStateEntriesByType(
                    stateSchema,
                    stateTypeForRequirement(requirementType),
                  )}
                  value={requirementStateKey}
                  placeholder="Search memory..."
                  onChange={setRequirementStateKey}
                />

                {requirementType === 'stat_check' && (
                  <>
                    <select
                      className="dialogue-effects__select"
                      value={requirementStatOp}
                      onChange={(event) =>
                        setRequirementStatOp(event.target.value as 'at_least' | 'less_than' | 'equals')
                      }
                    >
                      <option value="at_least">is at least</option>
                      <option value="less_than">is less than</option>
                      <option value="equals">equals</option>
                    </select>
                    <input
                      className="dialogue-effects__number"
                      type="number"
                      value={requirementValue}
                      onChange={(event) => setRequirementValue(Number(event.target.value))}
                    />
                  </>
                )}

                {requirementType === 'flag' && (
                  <select
                    className="dialogue-effects__select"
                    value={requirementFlagValue ? 'true' : 'false'}
                    onChange={(event) => setRequirementFlagValue(event.target.value === 'true')}
                  >
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </select>
                )}

                <button type="button" className="dialogue-effects__add" onClick={addRequirement}>
                  Add requirement
                </button>
              </div>

              {draftRequirements.length > 0 && (
                <div className="dialogue-effects__list">
                  {draftRequirements.map((requirement, index) => (
                    <span
                      key={`${requirement.type}-${requirement.state_key}-${index}`}
                      className="dialogue-badge dialogue-badge--requirement"
                    >
                      {getRequirementLabel(requirement, stateSchema)}
                      <button
                        type="button"
                        className="dialogue-badge__remove"
                        onClick={() => removeRequirement(index)}
                        aria-label="Remove requirement"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="dialogue-effects">
              <div className="dialogue-effects__header">When chosen, this will...</div>
              <div className="dialogue-effects__row">
                <select
                  className="dialogue-effects__select"
                  value={effectType}
                  onChange={(event) => setEffectType(event.target.value as DialogueEffect['type'])}
                >
                  <option value="remember_choice">Remember this choice</option>
                  <option value="give_item">Give player item</option>
                  <option value="remove_item">Remove player item</option>
                  <option value="change_stat">Change stat</option>
                  <option value="set_flag">Set flag</option>
                </select>
                <input
                  className="dialogue-effects__input"
                  value={effectLabel}
                  onChange={(event) => setEffectLabel(event.target.value)}
                  placeholder={
                    effectType === 'remember_choice'
                      ? 'Spared the Bandit'
                      : effectType === 'give_item' || effectType === 'remove_item'
                        ? 'Basement Key'
                        : effectType === 'change_stat'
                          ? 'Mara Trust'
                          : 'Alarm Active'
                  }
                />
                {effectType === 'change_stat' && (
                  <input
                    className="dialogue-effects__number"
                    type="number"
                    value={effectAmount}
                    onChange={(event) => setEffectAmount(Number(event.target.value))}
                  />
                )}
                {effectType === 'set_flag' && (
                  <select
                    className="dialogue-effects__select"
                    value={effectFlagValue ? 'true' : 'false'}
                    onChange={(event) => setEffectFlagValue(event.target.value === 'true')}
                  >
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </select>
                )}
                <button type="button" className="dialogue-effects__add" onClick={addEffect}>
                  Add effect
                </button>
              </div>

              {draftEffects.length > 0 && (
                <div className="dialogue-effects__list">
                  {draftEffects.map((effect, index) => (
                    <span key={`${effect.type}-${effect.state_key}-${index}`} className="dialogue-badge">
                      {getEffectLabel(effect)}
                      <button
                        type="button"
                        className="dialogue-badge__remove"
                        onClick={() => removeEffect(index)}
                        aria-label="Remove effect"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="dialogue-blob__speaker">{detail.character?.name ?? 'Unknown'}</div>
            <p className="dialogue-blob__text">{detail.text || '(no text)'}</p>

            <div className="dialogue-blob__meta">
              <span className="dialogue-blob__meta-label">Requirements</span>
              {draftRequirements.length ? (
                <div className="dialogue-effects__list">
                  {draftRequirements.map((requirement, index) => (
                    <span
                      key={`${requirement.type}-${requirement.state_key}-${index}`}
                      className="dialogue-badge dialogue-badge--requirement"
                    >
                      {getRequirementLabel(requirement, stateSchema)}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="dialogue-blob__meta-placeholder">No requirements yet</div>
              )}
            </div>

            <div className="dialogue-blob__meta">
              <span className="dialogue-blob__meta-label">Effects</span>
              {draftEffects.length ? (
                <div className="dialogue-effects__list">
                  {draftEffects.map((effect, index) => (
                    <span key={`${effect.type}-${effect.state_key}-${index}`} className="dialogue-badge">
                      {getEffectLabel(effect)}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="dialogue-blob__meta-placeholder">No effects yet</div>
              )}
            </div>
          </>
        )}
      </div>
    </article>
  );
}
