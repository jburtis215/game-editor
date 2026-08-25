import { useEffect, useRef, useState } from 'react';
import {
  api,
  API_BASE,
  type Character,
  type DialogueRequirement,
  type Location,
  type Scene,
  type StateSchema,
} from '../../api/client';
import { MemoryComboBox } from '../dialogue/MemoryComboBox';
import {
  getRequirementLabel,
  getStateEntriesByType,
  stateTypeForRequirement,
} from '../../lib/requirements';

/** The detail fields the card saves on a debounce (free text + small selects). */
type LocationFields = {
  kind: string;
  scale: string;
  mood: string;
  props: string[];
};

const KINDS = [
  { value: '', label: '—' },
  { value: 'interior', label: 'Interior' },
  { value: 'exterior', label: 'Exterior' },
];

const SCALES = [
  { value: '', label: '—' },
  { value: 'cramped', label: 'Cramped' },
  { value: 'room', label: 'Room' },
  { value: 'open', label: 'Open' },
  { value: 'vast', label: 'Vast' },
];

type RequirementKind = 'remembered_choice' | 'has_item' | 'stat_check' | 'flag';

interface LocationCardProps {
  location: Location;
  /** The project's characters — who can be placed here. */
  characters: Character[];
  /** The level's *other* locations — where this one can connect to. */
  siblings: Location[];
  /** The scenes set at this location. */
  scenes: Scene[];
  /** The project's story state — what a connection's requirement may reference. */
  stateSchema: StateSchema;
  onReplace: (location: Location) => void;
  /** A connection shows on both locations it joins, so the far end needs a reload. */
  onConnectionsChanged: () => void;
  onDelete: (id: number) => void;
  onAddScene: (id: number) => void;
  onOpenScene: (scene: Scene) => void;
  onError: (message: string | null) => void;
}

/**
 * One place in the world: its reference image, what it's like (kind/scale/mood/props), who's
 * there, where you can go from it, and the scenes set in it.
 */
export default function LocationCard({
  location,
  characters,
  siblings,
  scenes,
  stateSchema,
  onReplace,
  onConnectionsChanged,
  onDelete,
  onAddScene,
  onOpenScene,
  onError,
}: LocationCardProps) {
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(location.name);

  // Detail fields are edited continuously (a text input, a chip list), so they keep a local
  // working copy and save on a debounce — the same shape as the Settings tab's traits.
  const [fields, setFields] = useState<LocationFields>({
    kind: location.kind,
    scale: location.scale,
    mood: location.mood,
    props: location.props,
  });
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const t = setTimeout(() => {
      void api
        .PATCH('/api/locations/{location_id}', {
          params: { path: { location_id: location.id } },
          body: fields,
        })
        .then(({ data, error }) => {
          if (error || !data) return onError('Failed to save location');
          onError(null);
        });
    }, 400);
    return () => clearTimeout(t);
  }, [fields, location.id, onError]);

  const [propDraft, setPropDraft] = useState('');

  // Connection form.
  const [connTo, setConnTo] = useState('');
  const [connLabel, setConnLabel] = useState('');
  const [connBidirectional, setConnBidirectional] = useState(true);
  const [connReqs, setConnReqs] = useState<DialogueRequirement[]>([]);
  const [reqKind, setReqKind] = useState<RequirementKind>('has_item');
  const [reqStateKey, setReqStateKey] = useState('');
  const [reqOp, setReqOp] = useState<'at_least' | 'less_than' | 'equals'>('at_least');
  const [reqValue, setReqValue] = useState(1);
  const [reqFlagValue, setReqFlagValue] = useState(true);

  // Reference image.
  const fileRef = useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = useState('');
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [imgError, setImgError] = useState<string | null>(null);

  function setField<K extends keyof LocationFields>(key: K, value: LocationFields[K]) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  async function saveName() {
    const name = nameDraft.trim();
    if (!name) return;
    const { data, error } = await api.PATCH('/api/locations/{location_id}', {
      params: { path: { location_id: location.id } },
      body: { name },
    });
    if (error || !data) return onError('Failed to save location');
    onError(null);
    onReplace(data);
    setEditingName(false);
  }

  function addProp() {
    const prop = propDraft.trim();
    if (!prop || fields.props.includes(prop)) return setPropDraft('');
    setField('props', [...fields.props, prop]);
    setPropDraft('');
  }

  async function addCharacter(characterId: number) {
    const { data, error } = await api.POST('/api/locations/{location_id}/characters', {
      params: { path: { location_id: location.id } },
      body: { character_id: characterId },
    });
    if (error || !data) return onError('Failed to add character');
    onError(null);
    onReplace(data);
  }

  async function removeCharacter(characterId: number) {
    const { data, error } = await api.DELETE(
      '/api/locations/{location_id}/characters/{character_id}',
      { params: { path: { location_id: location.id, character_id: characterId } } },
    );
    if (error || !data) return onError('Failed to remove character');
    onError(null);
    onReplace(data);
  }

  /** Build one requirement from the picker and stage it on the connection being created. */
  function addRequirement() {
    if (!reqStateKey) return;
    const requirement: DialogueRequirement =
      reqKind === 'has_item'
        ? { type: 'has_item', state_key: reqStateKey }
        : reqKind === 'stat_check'
          ? { type: 'stat_check', state_key: reqStateKey, op: reqOp, value: reqValue }
          : { type: 'state_equals', state_key: reqStateKey, value: reqFlagValue };
    setConnReqs((prev) => [...prev, requirement]);
    setReqStateKey('');
  }

  async function connect() {
    const toId = Number(connTo);
    if (!toId) return;
    const { data, error } = await api.POST('/api/locations/{location_id}/connections', {
      params: { path: { location_id: location.id } },
      body: {
        to_id: toId,
        label: connLabel.trim(),
        bidirectional: connBidirectional,
        requirements: connReqs,
      },
    });
    if (error || !data) return onError('Failed to connect locations');
    onError(null);
    onReplace(data);
    onConnectionsChanged();
    setConnTo('');
    setConnLabel('');
    setConnReqs([]);
  }

  async function disconnect(connectionId: number) {
    const { data, error } = await api.DELETE(
      '/api/locations/{location_id}/connections/{connection_id}',
      { params: { path: { location_id: location.id, connection_id: connectionId } } },
    );
    if (error || !data) return onError('Failed to remove connection');
    onError(null);
    onReplace(data);
    onConnectionsChanged();
  }

  // Multipart upload via a direct fetch (openapi-fetch is awkward for file bodies).
  async function uploadImage(file: File) {
    setUploading(true);
    setImgError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE}/api/locations/${location.id}/image`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) return setImgError(data?.error ?? 'Upload failed');
      onReplace(data as Location);
    } catch {
      setImgError('Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function generateImage() {
    setGenerating(true);
    setImgError(null);
    const { data, error } = await api.POST('/api/locations/{location_id}/generate-image', {
      params: { path: { location_id: location.id } },
      body: { prompt: prompt.trim() || null },
    });
    setGenerating(false);
    if (error || !data) {
      return setImgError((error as { error?: string })?.error ?? 'Generation failed');
    }
    onReplace(data);
  }

  const presentIds = new Set(location.characters.map((c) => c.id));
  const available = characters.filter((c) => !presentIds.has(c.id));
  const connectedIds = new Set(location.connections.map((c) => c.other_id));
  const connectable = siblings.filter((l) => !connectedIds.has(l.id));

  return (
    <section className="loc-card">
      <header className="loc-card__head">
        {editingName ? (
          <form
            className="loc-card__edit"
            onSubmit={(e) => {
              e.preventDefault();
              void saveName();
            }}
          >
            <input
              className="loc-card__input"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              placeholder="Location name…"
              autoFocus
            />
            <button type="submit" className="btn btn--primary">
              Save
            </button>
            <button type="button" className="btn" onClick={() => setEditingName(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <>
            <span className="loc-card__icon">📍</span>
            <h2 className="loc-card__name">{location.name}</h2>
            <div className="loc-card__actions">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setNameDraft(location.name);
                  setEditingName(true);
                }}
              >
                Rename
              </button>
              <button type="button" className="btn" onClick={() => onDelete(location.id)}>
                Delete
              </button>
            </div>
          </>
        )}
      </header>

      {/* Reference image — the "best available representation" of this place. */}
      <div className="loc-art">
        <div className="loc-art__frame">
          {location.image_url ? (
            <img className="loc-art__img" src={location.image_url} alt={location.name} />
          ) : (
            <span className="loc-art__placeholder">No reference image yet</span>
          )}
        </div>
        <div className="loc-art__controls">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void uploadImage(f);
            }}
          />
          <button
            type="button"
            className="btn"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? 'Uploading…' : '⬆ Upload'}
          </button>
          <input
            className="loc-art__prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="AI prompt (optional — defaults to name, description + mood)"
          />
          <button
            type="button"
            className="btn btn--primary"
            disabled={generating}
            onClick={() => void generateImage()}
          >
            {generating ? 'Generating…' : '✨ Generate'}
          </button>
        </div>
        {imgError && <p className="loc-art__error">{imgError}</p>}
      </div>

      {/* What this place is like. */}
      <div className="loc-card__section">
        <h3 className="loc-card__section-title">What it's like</h3>
        <div className="loc-fields">
          <label className="loc-field">
            <span className="loc-field__label">Kind</span>
            <select
              className="loc-card__select"
              value={fields.kind}
              onChange={(e) => setField('kind', e.target.value)}
            >
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          <label className="loc-field">
            <span className="loc-field__label">Scale</span>
            <select
              className="loc-card__select"
              value={fields.scale}
              onChange={(e) => setField('scale', e.target.value)}
            >
              {SCALES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="loc-field loc-field--wide">
          <span className="loc-field__label">Mood</span>
          <input
            className="loc-card__input"
            value={fields.mood}
            onChange={(e) => setField('mood', e.target.value)}
            placeholder="smoky, candle-lit, too quiet"
          />
        </label>
      </div>

      {/* Props — the things in the room. */}
      <div className="loc-card__section">
        <h3 className="loc-card__section-title">Props here</h3>
        <div className="loc-chips">
          {fields.props.length === 0 && (
            <span className="loc-chips__empty">Nothing in it yet.</span>
          )}
          {fields.props.map((prop) => (
            <span key={prop} className="loc-chip loc-chip--prop">
              {prop}
              <button
                type="button"
                className="loc-chip__remove"
                aria-label={`Remove ${prop}`}
                onClick={() => setField('props', fields.props.filter((p) => p !== prop))}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
        <form
          className="loc-inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            addProp();
          }}
        >
          <input
            className="loc-card__input"
            value={propDraft}
            onChange={(e) => setPropDraft(e.target.value)}
            placeholder="bar counter, trapdoor behind the barrels…"
          />
          <button type="submit" className="btn btn--add">
            ＋ Add prop
          </button>
        </form>
      </div>

      {/* Characters present. */}
      <div className="loc-card__section">
        <h3 className="loc-card__section-title">Characters here</h3>
        <div className="loc-chips">
          {location.characters.length === 0 && (
            <span className="loc-chips__empty">Nobody here yet.</span>
          )}
          {location.characters.map((c) => (
            <span key={c.id} className="loc-chip">
              {c.name}
              <button
                type="button"
                className="loc-chip__remove"
                aria-label={`Remove ${c.name}`}
                onClick={() => void removeCharacter(c.id)}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
        {available.length > 0 && (
          <select
            className="loc-card__select"
            value=""
            onChange={(e) => {
              const val = Number(e.target.value);
              if (val) void addCharacter(val);
            }}
          >
            <option value="">＋ Add character…</option>
            {available.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Connections — the world graph. */}
      <div className="loc-card__section">
        <h3 className="loc-card__section-title">Connects to…</h3>
        <ul className="loc-conns">
          {location.connections.length === 0 && (
            <li className="loc-chips__empty">No way out of here yet.</li>
          )}
          {location.connections.map((conn) => (
            <li key={conn.id} className="loc-conn">
              <span className="loc-conn__arrow">{conn.bidirectional ? '⇄' : '→'}</span>
              <span className="loc-conn__body">
                <span className="loc-conn__name">{conn.other_name}</span>
                {conn.label && <span className="loc-conn__label">{conn.label}</span>}
                {conn.requirements.map((req, i) => (
                  <span key={i} className="loc-badge loc-badge--requirement">
                    🔒 {getRequirementLabel(req as DialogueRequirement, stateSchema)}
                  </span>
                ))}
                {conn.direction === 'in' && (
                  <span className="loc-conn__note">from {conn.other_name}</span>
                )}
              </span>
              <button
                type="button"
                className="loc-chip__remove"
                aria-label={`Remove connection to ${conn.other_name}`}
                onClick={() => void disconnect(conn.id)}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>

        {connectable.length > 0 && (
          <div className="loc-connect">
            <div className="loc-connect__row">
              <select
                className="loc-card__select"
                value={connTo}
                onChange={(e) => setConnTo(e.target.value)}
              >
                <option value="">Connect to…</option>
                {connectable.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
              <input
                className="loc-card__input"
                value={connLabel}
                onChange={(e) => setConnLabel(e.target.value)}
                placeholder="cellar door"
              />
              <label className="loc-connect__toggle">
                <input
                  type="checkbox"
                  checked={connBidirectional}
                  onChange={(e) => setConnBidirectional(e.target.checked)}
                />
                Both ways
              </label>
            </div>

            <div className="loc-connect__row">
              <span className="loc-connect__hint">Locked until…</span>
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
                    onChange={(e) =>
                      setReqOp(e.target.value as 'at_least' | 'less_than' | 'equals')
                    }
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
                Add lock
              </button>
            </div>

            {connReqs.length > 0 && (
              <div className="loc-chips">
                {connReqs.map((req, index) => (
                  <span key={index} className="loc-badge loc-badge--requirement">
                    🔒 {getRequirementLabel(req, stateSchema)}
                    <button
                      type="button"
                      className="loc-chip__remove"
                      aria-label="Remove lock"
                      onClick={() => setConnReqs((prev) => prev.filter((_, i) => i !== index))}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}

            <button
              type="button"
              className="btn btn--add"
              disabled={!connTo}
              onClick={() => void connect()}
            >
              ＋ Add connection
            </button>
          </div>
        )}
      </div>

      {/* Scenes set here. */}
      <div className="loc-card__section">
        <h3 className="loc-card__section-title">Scenes here</h3>
        <ul className="loc-scenes">
          {scenes.length === 0 && <li className="loc-scenes__empty">No scenes here yet.</li>}
          {scenes.map((s) => (
            <li key={s.id}>
              <button type="button" className="loc-scene" onClick={() => onOpenScene(s)}>
                <span className="loc-scene__name">{s.name}</span>
                <span className="loc-scene__chevron">›</span>
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="btn btn--add loc-card__add-scene"
          onClick={() => onAddScene(location.id)}
        >
          ＋ New scene
        </button>
      </div>
    </section>
  );
}
