import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, API_BASE, type Character, type CharacterDetail } from '../api/client';
import {
  normalizeCharacterTraits,
  normalizeTraitDefs,
  resolveTraits,
  type CharacterTraits,
  type TraitDef,
  type TraitValue,
} from '../lib/characterTraits';
import TraitControl from '../components/traits/TraitControl';
import TraitPicker from '../components/traits/TraitPicker';
import './CharacterDetail.css';

export default function CharacterDetailPage() {
  const { projectId, characterId } = useParams();
  const id = Number(characterId);

  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [others, setOthers] = useState<Character[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Add-relationship form state.
  const [relOtherId, setRelOtherId] = useState('');
  const [relLabel, setRelLabel] = useState('');

  // Portrait state.
  const [prompt, setPrompt] = useState('');
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [imgError, setImgError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Traits: the project's defaults are overlaid live over this character's own values.
  const [projectTraits, setProjectTraits] = useState<TraitDef[]>([]);
  const [traits, setTraits] = useState<CharacterTraits>({ values: {}, own: [] });
  // JSON of the traits we know the server already has — stops the debounce below from
  // re-saving what we just loaded (or just saved).
  const savedTraits = useRef('');

  // Traits mutate continuously (sliders), so they save on their own debounce rather than via the
  // identity Save button. The backend PATCH is partial, so sending only `traits` is safe.
  const applyDetail = useCallback((d: CharacterDetail) => {
    setDetail(d);
    setName(d.name);
    setDescription(d.description);
  }, []);

  const load = useCallback(() => {
    api
      .GET('/api/characters/{character_id}', { params: { path: { character_id: id } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load character');
        setError(null);
        applyDetail(data);
        const loaded = normalizeCharacterTraits(data.traits);
        savedTraits.current = JSON.stringify(loaded);
        setTraits(loaded);
      });
  }, [id, applyDetail]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const json = JSON.stringify(traits);
    if (json === savedTraits.current) return;
    const t = setTimeout(() => {
      savedTraits.current = json;
      void api
        .PATCH('/api/characters/{character_id}', {
          params: { path: { character_id: id } },
          body: { traits },
        })
        .then(({ data, error }) => {
          if (error || !data) return setError('Failed to save traits');
          setError(null);
          setDetail(data);
        });
    }, 400);
    return () => clearTimeout(t);
  }, [traits, id]);

  // The project's other characters power the relationship dropdown.
  useEffect(() => {
    if (!projectId) return;
    api
      .GET('/api/characters', { params: { query: { project_id: Number(projectId) } } })
      .then(({ data }) => data && setOthers(data.filter((c) => c.id !== id)));
  }, [projectId, id]);

  // The project's default traits — this page is outside the tab layout, so there's no useProject().
  useEffect(() => {
    if (!projectId) return;
    api
      .GET('/api/projects/{project_id}', { params: { path: { project_id: Number(projectId) } } })
      .then(({ data }) => data && setProjectTraits(normalizeTraitDefs(data.character_traits)));
  }, [projectId]);

  const resolvedTraits = useMemo(
    () => resolveTraits(projectTraits, traits),
    [projectTraits, traits],
  );

  function setTraitValue(key: string, value: TraitValue) {
    setTraits((prev) => ({ ...prev, values: { ...prev.values, [key]: value } }));
  }

  /** Drop the character's override so the trait falls back to the project's default value. */
  function resetTraitValue(key: string) {
    setTraits((prev) => {
      const values = { ...prev.values };
      delete values[key];
      return { ...prev, values };
    });
  }

  function removeOwnTrait(key: string) {
    setTraits((prev) => {
      const values = { ...prev.values };
      delete values[key];
      return { values, own: prev.own.filter((t) => t.key !== key) };
    });
  }

  function addOwnTrait(def: TraitDef) {
    setTraits((prev) =>
      prev.own.some((t) => t.key === def.key)
        ? prev
        : { values: { ...prev.values, [def.key]: def.default }, own: [...prev.own, def] },
    );
  }

  async function saveIdentity() {
    const { data, error } = await api.PATCH('/api/characters/{character_id}', {
      params: { path: { character_id: id } },
      body: { name: name.trim() || 'Unnamed', description },
    });
    if (error || !data) return setError('Failed to save character');
    setError(null);
    applyDetail(data);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  async function addRelationship(e: React.FormEvent) {
    e.preventDefault();
    if (!relOtherId) return;
    const { data, error } = await api.POST('/api/characters/{character_id}/relationships', {
      params: { path: { character_id: id } },
      body: { other_id: Number(relOtherId), relationship: relLabel.trim() },
    });
    if (error || !data) return setError('Failed to add relationship');
    setError(null);
    applyDetail(data);
    setRelOtherId('');
    setRelLabel('');
  }

  async function removeRelationship(relationshipId: number) {
    const { error } = await api.DELETE(
      '/api/characters/{character_id}/relationships/{relationship_id}',
      { params: { path: { character_id: id, relationship_id: relationshipId } } },
    );
    if (error) return setError('Failed to remove relationship');
    setError(null);
    load();
  }

  // Multipart upload via a direct fetch (openapi-fetch is awkward for file bodies).
  async function uploadImage(file: File) {
    setUploading(true);
    setImgError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API_BASE}/api/characters/${id}/image`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) return setImgError(data?.error ?? 'Upload failed');
      applyDetail(data as CharacterDetail);
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
    const { data, error } = await api.POST('/api/characters/{character_id}/generate-image', {
      params: { path: { character_id: id } },
      body: { prompt: prompt.trim() || null },
    });
    setGenerating(false);
    if (error || !data) return setImgError((error as { error?: string })?.error ?? 'Generation failed');
    applyDetail(data);
  }

  return (
    <div className="char-detail">
      <Link to={`/projects/${projectId}/characters`} className="char-detail__back">
        ← Characters
      </Link>

      {error && <p className="char-detail__error">{error}</p>}

      <header className="char-detail__header">
        <div className="char-detail__avatar">
          {detail?.image_url ? (
            <img className="char-detail__avatar-img" src={detail.image_url} alt="" />
          ) : (
            (name[0] ?? '?').toUpperCase()
          )}
        </div>
        <h1 className="char-detail__title">{name || 'Character'}</h1>
      </header>

      {detail && (
        <>
          <section className="char-section char-portrait">
            <h2 className="char-section__title">Portrait</h2>
            <div className="char-portrait__body">
              <div className="char-portrait__frame">
                {detail.image_url ? (
                  <img className="char-portrait__img" src={detail.image_url} alt={name} />
                ) : (
                  <span className="char-portrait__placeholder">
                    {(name[0] ?? '?').toUpperCase()}
                  </span>
                )}
              </div>
              <div className="char-portrait__controls">
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadImage(f);
                  }}
                />
                <button
                  type="button"
                  className="btn"
                  disabled={uploading}
                  onClick={() => fileRef.current?.click()}
                >
                  {uploading ? 'Uploading…' : '⬆ Upload image'}
                </button>

                <div className="char-portrait__ai">
                  <input
                    className="char-portrait__prompt"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="AI prompt (optional — defaults to name + description)"
                  />
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={generating}
                    onClick={generateImage}
                  >
                    {generating ? 'Generating…' : '✨ Generate with AI'}
                  </button>
                </div>

                {imgError && <p className="char-portrait__error">{imgError}</p>}
              </div>
            </div>
          </section>

          <section className="char-section">
            <h2 className="char-section__title">Identity</h2>
            <label className="char-field">
              <span className="char-field__label">Name</span>
              <input
                className="char-field__input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Character name…"
              />
            </label>
            <label className="char-field">
              <span className="char-field__label">Description</span>
              <textarea
                className="char-field__textarea"
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Who is this character? Backstory, personality, role…"
              />
            </label>
            <div className="char-section__actions">
              <button type="button" className="btn btn--primary" onClick={saveIdentity}>
                {saved ? 'Saved ✓' : 'Save'}
              </button>
            </div>
          </section>

          <section className="char-section">
            <h2 className="char-section__title">Relationships</h2>
            <p className="char-section__hint">
              Directed — how <strong>{name || 'this character'}</strong> relates to others. Shown
              only here; add the reverse on the other character if you want it there too.
            </p>
            {detail.related.length === 0 ? (
              <p className="char-section__empty">No relationships yet.</p>
            ) : (
              <ul className="char-rel-list">
                {detail.related.map((r) => (
                  <li key={r.relationship_id} className="char-rel">
                    <span className="char-rel__label">{r.relationship || 'related to'}</span>
                    <span className="char-rel__arrow">→</span>
                    <Link
                      to={`/projects/${projectId}/characters/${r.id}`}
                      className="char-rel__name"
                    >
                      {r.name}
                    </Link>
                    <button
                      type="button"
                      className="char-rel__remove"
                      aria-label={`Remove relationship to ${r.name}`}
                      onClick={() => removeRelationship(r.relationship_id)}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <form className="char-rel-add" onSubmit={addRelationship}>
              <input
                className="char-rel-add__label"
                value={relLabel}
                onChange={(e) => setRelLabel(e.target.value)}
                placeholder="Relationship (e.g. mentor of)"
              />
              <span className="char-rel-add__arrow">→</span>
              <select
                className="char-rel-add__select"
                value={relOtherId}
                onChange={(e) => setRelOtherId(e.target.value)}
              >
                <option value="">Character…</option>
                {others.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
              <button type="submit" className="btn btn--add" disabled={!relOtherId}>
                ＋ Add
              </button>
            </form>
          </section>

          <section className="char-section">
            <h2 className="char-section__title">Traits</h2>
            <p className="char-section__hint">
              Traits marked <em>default</em> come from the project's{' '}
              <Link to={`/projects/${projectId}/settings`}>Settings</Link> and apply to every
              character — change the value here to override it just for {name || 'this character'}.
              Traits added below belong to this character alone.
            </p>

            {resolvedTraits.length === 0 ? (
              <p className="char-section__empty">
                No traits yet. Add one below, or set project-wide defaults in Settings.
              </p>
            ) : (
              <div className="trait-list">
                {resolvedTraits.map((t) => (
                  <TraitControl
                    key={t.def.key}
                    def={t.def}
                    value={t.value}
                    badge={t.source === 'project' ? 'default' : undefined}
                    onChange={(v) => setTraitValue(t.def.key, v)}
                    actions={
                      t.source === 'project' ? (
                        <button
                          type="button"
                          className="trait-row__action"
                          aria-label={`Reset ${t.def.label} to the project default`}
                          title="Reset to the project default"
                          disabled={!t.overridden}
                          onClick={() => resetTraitValue(t.def.key)}
                        >
                          ↺
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="trait-row__action"
                          aria-label={`Remove ${t.def.label}`}
                          title="Remove this trait"
                          onClick={() => removeOwnTrait(t.def.key)}
                        >
                          ✕
                        </button>
                      )
                    }
                  />
                ))}
              </div>
            )}

            <TraitPicker
              taken={resolvedTraits.map((t) => t.def.key)}
              hint="Add a trait only this character has."
              onAdd={addOwnTrait}
            />
          </section>
        </>
      )}
    </div>
  );
}
