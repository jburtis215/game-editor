import { useEffect, useRef, useState } from 'react';
import { api, type Ability, type DialogueRequirement, type StateSchema } from '../../api/client';
import {
  defaultParamValue,
  normalizeParams,
  paramKey,
  paramLabel,
  PARAM_TYPES,
  type AbilityParams,
  type ParamType,
  type ParamValue,
} from '../../lib/abilities';
import { MemoryComboBox } from '../dialogue/MemoryComboBox';
import {
  getRequirementLabel,
  getStateEntriesByType,
  stateTypeForRequirement,
} from '../../lib/requirements';

type RequirementKind = 'remembered_choice' | 'has_item' | 'stat_check' | 'flag';

/** Everything on the card saves together on one debounce. */
type AbilityFields = {
  name: string;
  description: string;
  params: AbilityParams;
  unlock_requirements: DialogueRequirement[];
};

interface AbilityCardProps {
  ability: Ability;
  /** The project's story state — what an unlock requirement may reference. */
  stateSchema: StateSchema;
  onDelete: (id: number) => void;
  onError: (message: string | null) => void;
}

/** One player verb: what it is, the knobs that tune it, and what unlocks it. */
export default function AbilityCard({
  ability,
  stateSchema,
  onDelete,
  onError,
}: AbilityCardProps) {
  const [fields, setFields] = useState<AbilityFields>({
    name: ability.name,
    description: ability.description,
    params: normalizeParams(ability.params),
    unlock_requirements: (ability.unlock_requirements ?? []) as DialogueRequirement[],
  });

  // Every field here is typed continuously (text inputs, a slider-ish number box), so the
  // card keeps a working copy and saves on a debounce — same shape as the Settings tab.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const t = setTimeout(() => {
      void api
        .PATCH('/api/abilities/{ability_id}', {
          params: { path: { ability_id: ability.id } },
          body: fields,
        })
        .then(({ error }) => onError(error ? 'Failed to save ability' : null));
    }, 400);
    return () => clearTimeout(t);
  }, [fields, ability.id, onError]);

  // New-param form.
  const [paramName, setParamName] = useState('');
  const [paramType, setParamType] = useState<ParamType>('number');

  // Unlock-requirement picker (the same controls as the dialogue/connection ones).
  const [reqKind, setReqKind] = useState<RequirementKind>('has_item');
  const [reqStateKey, setReqStateKey] = useState('');
  const [reqOp, setReqOp] = useState<'at_least' | 'less_than' | 'equals'>('at_least');
  const [reqValue, setReqValue] = useState(1);
  const [reqFlagValue, setReqFlagValue] = useState(true);

  function setField<K extends keyof AbilityFields>(key: K, value: AbilityFields[K]) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  function setParam(key: string, value: ParamValue) {
    setFields((prev) => ({ ...prev, params: { ...prev.params, [key]: value } }));
  }

  function addParam() {
    const key = paramKey(paramName);
    if (!key || key in fields.params) return setParamName('');
    setParam(key, defaultParamValue(paramType));
    setParamName('');
  }

  function removeParam(key: string) {
    setFields((prev) => {
      const params = { ...prev.params };
      delete params[key];
      return { ...prev, params };
    });
  }

  /** Build one requirement from the picker and add it to this ability's unlock gate. */
  function addRequirement() {
    if (!reqStateKey) return;
    const requirement: DialogueRequirement =
      reqKind === 'has_item'
        ? { type: 'has_item', state_key: reqStateKey }
        : reqKind === 'stat_check'
          ? { type: 'stat_check', state_key: reqStateKey, op: reqOp, value: reqValue }
          : { type: 'state_equals', state_key: reqStateKey, value: reqFlagValue };
    setField('unlock_requirements', [...fields.unlock_requirements, requirement]);
    setReqStateKey('');
  }

  const paramEntries = Object.entries(fields.params);

  return (
    <section className="pab-card">
      <header className="pab-card__head">
        <input
          className="pab-card__name"
          value={fields.name}
          onChange={(e) => setField('name', e.target.value)}
          placeholder="Dash"
        />
        <button
          type="button"
          className="btn"
          onClick={() => onDelete(ability.id)}
          aria-label={`Delete ${ability.name}`}
        >
          Delete
        </button>
      </header>

      <textarea
        className="pab-card__desc"
        rows={2}
        value={fields.description}
        onChange={(e) => setField('description', e.target.value)}
        placeholder="What it does, in plain language — short burst forward, brief invulnerability"
      />

      {/* Params — the knobs that tune this one verb. */}
      <div className="pab-card__section">
        <h4 className="pab-card__section-title">Tuning</h4>
        {paramEntries.length === 0 && <p className="pab-card__empty">No params yet.</p>}
        <div className="pab-params">
          {paramEntries.map(([key, value]) => (
            <div key={key} className="pab-param">
              <span className="pab-param__key">{paramLabel(key)}</span>
              {typeof value === 'boolean' ? (
                <select
                  className="dialogue-effects__select"
                  value={value ? 'true' : 'false'}
                  onChange={(e) => setParam(key, e.target.value === 'true')}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              ) : typeof value === 'number' ? (
                <input
                  className="dialogue-effects__number"
                  type="number"
                  step="any"
                  value={value}
                  onChange={(e) => setParam(key, Number(e.target.value))}
                />
              ) : (
                <input
                  className="pab-param__text"
                  value={value}
                  onChange={(e) => setParam(key, e.target.value)}
                />
              )}
              <button
                type="button"
                className="pab-chip__remove"
                aria-label={`Remove ${paramLabel(key)}`}
                onClick={() => removeParam(key)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <form
          className="pab-card__row"
          onSubmit={(e) => {
            e.preventDefault();
            addParam();
          }}
        >
          <input
            className="pab-param__text"
            value={paramName}
            onChange={(e) => setParamName(e.target.value)}
            placeholder="cooldown, distance, uses…"
          />
          <select
            className="dialogue-effects__select"
            value={paramType}
            onChange={(e) => setParamType(e.target.value as ParamType)}
          >
            {PARAM_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          <button type="submit" className="btn btn--add">
            ＋ Add param
          </button>
        </form>
      </div>

      {/* Unlock gate — ability gating, the mechanic half of lock-and-key design. */}
      <div className="pab-card__section">
        <h4 className="pab-card__section-title">Unlocks when…</h4>
        <div className="pab-chips">
          {fields.unlock_requirements.length === 0 && (
            <span className="pab-card__empty">Available from the start.</span>
          )}
          {fields.unlock_requirements.map((req, index) => (
            <span key={index} className="pab-badge">
              🔒 {getRequirementLabel(req, stateSchema)}
              <button
                type="button"
                className="pab-chip__remove"
                aria-label="Remove unlock requirement"
                onClick={() =>
                  setField(
                    'unlock_requirements',
                    fields.unlock_requirements.filter((_, i) => i !== index),
                  )
                }
              >
                ✕
              </button>
            </span>
          ))}
        </div>
        <div className="pab-card__row">
          <select
            className="dialogue-effects__select"
            value={reqKind}
            onChange={(e) => {
              setReqKind(e.target.value as RequirementKind);
              setReqStateKey('');
            }}
          >
            <option value="has_item">Player has item</option>
            <option value="remembered_choice">Player previously chose</option>
            <option value="stat_check">Stat check</option>
            <option value="flag">Flag is</option>
          </select>
          <MemoryComboBox
            entries={getStateEntriesByType(stateSchema, stateTypeForRequirement(reqKind))}
            value={reqStateKey}
            onChange={setReqStateKey}
          />
          {reqKind === 'stat_check' && (
            <>
              <select
                className="dialogue-effects__select"
                value={reqOp}
                onChange={(e) => setReqOp(e.target.value as 'at_least' | 'less_than' | 'equals')}
              >
                <option value="at_least">is at least</option>
                <option value="less_than">is less than</option>
                <option value="equals">equals</option>
              </select>
              <input
                className="dialogue-effects__number"
                type="number"
                value={reqValue}
                onChange={(e) => setReqValue(Number(e.target.value))}
              />
            </>
          )}
          {reqKind === 'flag' && (
            <select
              className="dialogue-effects__select"
              value={reqFlagValue ? 'true' : 'false'}
              onChange={(e) => setReqFlagValue(e.target.value === 'true')}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          )}
          <button type="button" className="dialogue-effects__add" onClick={addRequirement}>
            Add unlock
          </button>
        </div>
      </div>
    </section>
  );
}
