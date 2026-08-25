import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, API_BASE, type EntityType } from '../api/client';
import './Entities.css';

const CATEGORIES = ['enemy', 'hazard', 'pickup', 'prop'] as const;
const PATTERNS = ['static', 'walk', 'patrol', 'fly'] as const;

type Behavior = {
  pattern?: string;
  speed?: number;
  harmful_on_touch?: boolean;
  stompable?: boolean;
};

/** The project's level palette: placeable enemies/hazards/pickups/props with glyphs. */
export default function EntitiesPage() {
  const { projectId } = useParams();
  const [entities, setEntities] = useState<EntityType[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const selected = entities.find((e) => e.id === selectedId) ?? null;

  async function reload(selectId?: number) {
    const { data, error } = await api.GET('/api/entities', {
      params: { query: { project_id: Number(projectId) } },
    });
    if (error || !data) return setError('Failed to load entities');
    setError(null);
    setEntities(data);
    if (selectId !== undefined) setSelectedId(selectId);
    else if (data.length && !data.some((e) => e.id === selectedId)) setSelectedId(data[0].id);
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function addEntity() {
    // pick the first free single letter as a glyph suggestion
    const used = new Set(entities.map((e) => e.glyph));
    const glyph = 'abcdfghijklmnqrstuvwxyz'.split('').find((c) => !used.has(c)) ?? 'z';
    const { data, error } = await api.POST('/api/entities', {
      body: { project_id: Number(projectId), name: `New entity ${entities.length + 1}`, glyph, category: 'enemy', description: '', behavior: { pattern: 'static', harmful_on_touch: false, stompable: false } },
    });
    if (error || !data) return setError('Failed to add entity');
    await reload(data.id);
  }

  async function seedStarter() {
    const { data, error } = await api.POST('/api/projects/{project_id}/seed-entities', {
      params: { path: { project_id: Number(projectId) } },
    });
    if (error || !data) return setError('Failed to add starter set');
    setError(null);
    setEntities(data);
    if (data.length) setSelectedId(data[0].id);
  }

  async function patch(id: number, body: Record<string, unknown>) {
    const { data, error } = await api.PATCH('/api/entities/{entity_id}', {
      params: { path: { entity_id: id } },
      body,
    });
    if (error || !data) return setError((error as { error?: string })?.error ?? 'Save failed');
    setError(null);
    setEntities((prev) => prev.map((e) => (e.id === id ? data : e)));
  }

  async function remove(id: number) {
    await api.DELETE('/api/entities/{entity_id}', { params: { path: { entity_id: id } } });
    await reload();
  }

  async function generateImage() {
    if (!selected) return;
    setBusy(true);
    const { data, error } = await api.POST('/api/entities/{entity_id}/generate-image', {
      params: { path: { entity_id: selected.id } },
      body: { prompt: null },
    });
    setBusy(false);
    if (error || !data) return setError((error as { error?: string })?.error ?? 'Generation failed');
    setError(null);
    setEntities((prev) => prev.map((e) => (e.id === data.id ? data : e)));
  }

  async function uploadImage(file: File) {
    if (!selected) return;
    setBusy(true);
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/entities/${selected.id}/image`, {
      method: 'POST',
      body: form,
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      return setError(body?.error ?? 'Upload failed');
    }
    const data = (await res.json()) as EntityType;
    setError(null);
    setEntities((prev) => prev.map((e) => (e.id === data.id ? data : e)));
  }

  const behavior: Behavior = (selected?.behavior as Behavior) ?? {};
  const setBehavior = (partial: Behavior) => {
    if (!selected) return;
    void patch(selected.id, { behavior: { ...behavior, ...partial } });
  };

  return (
    <div className="entities-page">
      <div className="entities-page__head">
        <h1 className="entities-page__title">Entities</h1>
        <div className="entities-page__actions">
          <button type="button" className="btn" onClick={seedStarter}>
            Add starter set
          </button>
          <button type="button" className="btn btn--add" onClick={addEntity}>
            ＋ New entity
          </button>
        </div>
      </div>
      <p className="entities-page__lead">
        The placeable things in your levels — enemies, hazards, pickups, props. Each has a
        one-character <strong>glyph</strong> used to paint it into level layouts.
      </p>
      {error && <p className="entities-page__error">{error}</p>}

      <div className="entities-page__body">
        <div className="entities-list">
          {entities.length === 0 && (
            <p className="entities-page__empty">No entities yet — add the starter set.</p>
          )}
          {entities.map((e) => (
            <button
              key={e.id}
              type="button"
              className={'entity-row' + (e.id === selectedId ? ' entity-row--active' : '')}
              onClick={() => setSelectedId(e.id)}
            >
              <span className="entity-row__glyph">{e.glyph}</span>
              <span className="entity-row__name">{e.name}</span>
              <span className={`entity-row__cat entity-row__cat--${e.category}`}>{e.category}</span>
            </button>
          ))}
        </div>

        {selected && (
          <div className="entity-editor">
            <div className="entity-editor__row">
              <label className="entity-editor__label">
                Name
                <input
                  className="entity-editor__input"
                  value={selected.name}
                  onChange={(ev) =>
                    setEntities((prev) =>
                      prev.map((e) => (e.id === selected.id ? { ...e, name: ev.target.value } : e)),
                    )
                  }
                  onBlur={(ev) => void patch(selected.id, { name: ev.target.value })}
                />
              </label>
              <label className="entity-editor__label entity-editor__label--glyph">
                Glyph
                <input
                  className="entity-editor__input entity-editor__input--glyph"
                  value={selected.glyph}
                  maxLength={1}
                  onChange={(ev) => {
                    const g = ev.target.value;
                    if (g) void patch(selected.id, { glyph: g });
                  }}
                />
              </label>
              <label className="entity-editor__label">
                Category
                <select
                  className="entity-editor__input"
                  value={selected.category}
                  onChange={(ev) => void patch(selected.id, { category: ev.target.value })}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="entity-editor__label">
              Description
              <textarea
                className="entity-editor__input entity-editor__textarea"
                value={selected.description ?? ''}
                rows={2}
                placeholder="What is it, how does it act? Free-form notes for the builder."
                onChange={(ev) =>
                  setEntities((prev) =>
                    prev.map((e) =>
                      e.id === selected.id ? { ...e, description: ev.target.value } : e,
                    ),
                  )
                }
                onBlur={(ev) => void patch(selected.id, { description: ev.target.value })}
              />
            </label>

            <div className="entity-editor__behavior">
              <div className="entity-editor__behavior-title">Behavior</div>
              <div className="entity-editor__row">
                <label className="entity-editor__label">
                  Pattern
                  <select
                    className="entity-editor__input"
                    value={behavior.pattern ?? 'static'}
                    onChange={(ev) => setBehavior({ pattern: ev.target.value })}
                  >
                    {PATTERNS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="entity-editor__label">
                  Speed (units/sec)
                  <input
                    type="number"
                    min={0}
                    max={20}
                    className="entity-editor__input"
                    value={behavior.speed ?? 0}
                    onChange={(ev) => setBehavior({ speed: Number(ev.target.value) })}
                  />
                </label>
              </div>
              <div className="entity-editor__row">
                <label className="entity-editor__check">
                  <input
                    type="checkbox"
                    checked={behavior.harmful_on_touch ?? false}
                    onChange={(ev) => setBehavior({ harmful_on_touch: ev.target.checked })}
                  />
                  Harmful on touch
                </label>
                <label className="entity-editor__check">
                  <input
                    type="checkbox"
                    checked={behavior.stompable ?? false}
                    onChange={(ev) => setBehavior({ stompable: ev.target.checked })}
                  />
                  Stompable (jump on top defeats it)
                </label>
              </div>
            </div>

            <div className="entity-editor__image">
              <div className="entity-editor__avatar">
                {selected.image_url ? (
                  <img src={selected.image_url} alt="" />
                ) : (
                  <span className="entity-editor__avatar-glyph">{selected.glyph}</span>
                )}
              </div>
              <div className="entity-editor__image-actions">
                <button type="button" className="btn" disabled={busy} onClick={() => void generateImage()}>
                  {busy ? 'Working…' : '✨ Generate image'}
                </button>
                <button type="button" className="btn" disabled={busy} onClick={() => fileInput.current?.click()}>
                  Upload image
                </button>
                <input
                  ref={fileInput}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(ev) => {
                    const f = ev.target.files?.[0];
                    if (f) void uploadImage(f);
                    ev.target.value = '';
                  }}
                />
              </div>
            </div>

            <button
              type="button"
              className="btn entity-editor__delete"
              onClick={() => void remove(selected.id)}
            >
              Delete entity
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
