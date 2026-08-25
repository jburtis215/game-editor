import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, BUILTIN_TILES, type EntityType, type Level, type LevelLayout, type Scene } from '../api/client';
import './LevelLayout.css';

const DEFAULT_W = 24;
const DEFAULT_H = 12;

function emptyLayout(): LevelLayout {
  const rows = Array.from({ length: DEFAULT_H }, (_, y) =>
    (y >= DEFAULT_H - 2 ? '#' : '.').repeat(DEFAULT_W),
  );
  return { width: DEFAULT_W, height: DEFAULT_H, rows };
}

function normalizeLayout(raw: unknown): LevelLayout | null {
  const l = raw as Partial<LevelLayout> | null;
  if (!l || !Array.isArray(l.rows) || !l.rows.length) return null;
  return { width: l.width ?? l.rows[0].length, height: l.height ?? l.rows.length, rows: l.rows };
}

function resize(layout: LevelLayout, width: number, height: number): LevelLayout {
  const rows = Array.from({ length: height }, (_, y) => {
    const row = layout.rows[y] ?? '';
    return (row + '.'.repeat(Math.max(0, width - row.length))).slice(0, width);
  });
  return { width, height, rows };
}

/** Paint-editor for a level's ASCII tile grid. One cell = one game unit. */
export default function LevelLayoutPage() {
  const { projectId, levelId } = useParams();
  const [level, setLevel] = useState<Level | null>(null);
  const [layout, setLayout] = useState<LevelLayout>(emptyLayout);
  const [entities, setEntities] = useState<EntityType[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [brush, setBrush] = useState<string>('#');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(true);
  const painting = useRef(false);

  const skipNextSave = useRef(false);
  useEffect(() => {
    if (!levelId) return;
    api
      .GET('/api/levels/{level_id}', { params: { path: { level_id: Number(levelId) } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load level');
        setLevel(data);
        const existing = normalizeLayout(data.layout);
        if (existing) {
          skipNextSave.current = true; // applying the fetched layout is not an edit
          setLayout(existing);
        }
      });
    api
      .GET('/api/entities', { params: { query: { project_id: Number(projectId) } } })
      .then(({ data }) => setEntities(data ?? []));
    api.GET('/api/scenes', { params: {} }).then(({ data }) => {
      setScenes((data ?? []).filter((s) => s.level_id === Number(levelId)));
    });
  }, [levelId, projectId]);

  // Debounced save of the grid.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    setSaved(false);
    const t = setTimeout(async () => {
      const { error } = await api.PATCH('/api/levels/{level_id}', {
        params: { path: { level_id: Number(levelId) } },
        body: { layout },
      });
      if (error) setError((error as { error?: string })?.error ?? 'Save failed');
      else {
        setError(null);
        setSaved(true);
      }
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);

  const paint = (x: number, y: number) => {
    setLayout((prev) => {
      const rows = [...prev.rows];
      const row = rows[y];
      if (!row || row[x] === brush) return prev;
      // P and G are unique: painting a new one erases the old one.
      if (brush === 'P' || brush === 'G') {
        for (let i = 0; i < rows.length; i++) {
          if (rows[i].includes(brush)) rows[i] = rows[i].split(brush).join('.');
        }
      }
      rows[y] = rows[y].slice(0, x) + brush + rows[y].slice(x + 1);
      return { ...prev, rows };
    });
  };

  async function setIntroScene(sceneId: string) {
    const { data, error } = await api.PATCH('/api/levels/{level_id}', {
      params: { path: { level_id: Number(levelId) } },
      body: { intro_scene_id: sceneId ? Number(sceneId) : null },
    });
    if (error || !data) return setError('Failed to set intro scene');
    setError(null);
    setLevel(data);
  }

  const entityByGlyph = useMemo(
    () => Object.fromEntries(entities.map((e) => [e.glyph, e])),
    [entities],
  );

  const cellClass = (ch: string) => {
    if (ch === '#') return 'cell cell--ground';
    if (ch === '=') return 'cell cell--platform';
    if (ch === 'P') return 'cell cell--player';
    if (ch === 'G') return 'cell cell--goal';
    if (ch === '.') return 'cell';
    const cat = entityByGlyph[ch]?.category;
    return 'cell ' + (cat === 'pickup' ? 'cell--pickup' : cat === 'prop' ? 'cell--prop' : 'cell--enemy');
  };

  return (
    <div className="layout-page" onMouseUp={() => (painting.current = false)} onMouseLeave={() => (painting.current = false)}>
      <div className="layout-page__head">
        <div>
          <Link to={`/projects/${projectId}/levels/${levelId}`} className="layout-page__back">
            ← {level?.name ?? 'Level'}
          </Link>
          <h1 className="layout-page__title">Layout</h1>
        </div>
        <div className="layout-page__meta">
          <label className="layout-page__field">
            Intro dialogue
            <select
              value={level?.intro_scene_id ?? ''}
              onChange={(ev) => void setIntroScene(ev.target.value)}
            >
              <option value="">— none —</option>
              {scenes.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="layout-page__field">
            Width
            <input
              type="number"
              min={8}
              max={120}
              value={layout.width}
              onChange={(ev) => setLayout((p) => resize(p, Math.max(8, Math.min(120, Number(ev.target.value) || 8)), p.height))}
            />
          </label>
          <label className="layout-page__field">
            Height
            <input
              type="number"
              min={4}
              max={40}
              value={layout.height}
              onChange={(ev) => setLayout((p) => resize(p, p.width, Math.max(4, Math.min(40, Number(ev.target.value) || 4))))}
            />
          </label>
          <span className={'layout-page__saved' + (saved ? '' : ' layout-page__saved--dirty')}>
            {saved ? 'Saved' : 'Saving…'}
          </span>
        </div>
      </div>
      {error && <p className="layout-page__error">{error}</p>}

      <div className="layout-page__body">
        <div className="layout-palette">
          <div className="layout-palette__section">Tiles</div>
          {BUILTIN_TILES.map((t) => (
            <button
              key={t.glyph}
              type="button"
              className={'palette-btn' + (brush === t.glyph ? ' palette-btn--active' : '')}
              onClick={() => setBrush(t.glyph)}
            >
              <span className={cellClass(t.glyph) + ' palette-btn__swatch'}>{t.glyph === '.' ? '' : t.glyph}</span>
              {t.name}
            </button>
          ))}
          <div className="layout-palette__section">Entities</div>
          {entities.length === 0 && (
            <p className="layout-palette__empty">
              None yet — add some in the project's <Link to={`/projects/${projectId}/entities`}>Entities</Link> tab.
            </p>
          )}
          {entities.map((e) => (
            <button
              key={e.id}
              type="button"
              className={'palette-btn' + (brush === e.glyph ? ' palette-btn--active' : '')}
              onClick={() => setBrush(e.glyph)}
            >
              <span className={cellClass(e.glyph) + ' palette-btn__swatch'}>{e.glyph}</span>
              {e.name}
            </button>
          ))}
        </div>

        <div className="layout-grid-wrap">
          <div
            className="layout-grid"
            style={{ gridTemplateColumns: `repeat(${layout.width}, 22px)` }}
            onMouseDown={() => (painting.current = true)}
          >
            {layout.rows.map((row, y) =>
              row.split('').map((ch, x) => (
                <button
                  key={`${x}-${y}`}
                  type="button"
                  className={cellClass(ch)}
                  onMouseDown={() => paint(x, y)}
                  onMouseEnter={() => painting.current && paint(x, y)}
                  title={`(${x}, ${y})`}
                >
                  {ch !== '.' && ch !== '#' ? ch : ''}
                </button>
              )),
            )}
          </div>
          <p className="layout-page__hint">
            Click or drag to paint with the selected glyph. One cell = one game unit (a 3-unit
            jump clears a 3-cell wall). Paint <strong>P</strong> for the player start and{' '}
            <strong>G</strong> for the goal — each level needs one of each.
          </p>
        </div>
      </div>
    </div>
  );
}
