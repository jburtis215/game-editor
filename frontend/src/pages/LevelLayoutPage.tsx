import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  api,
  BUILTIN_TILES,
  type EntityType,
  type Level,
  type LevelLayout,
  type Location,
  type Scene,
  type TileType,
} from '../api/client';
import './LevelLayout.css';

const DEFAULT_W = 24;
const DEFAULT_H = 12;

// The grid is 22px cells with a 1px gap, so one cell of pitch is 23px. Location overlays are
// absolutely positioned over the same grid and have to use the identical arithmetic, or a box
// drawn on cell 30 would sit a few pixels off the cell it names.
const CELL = 22;
const PITCH = CELL + 1;

type Rect = { x: number; y: number; width: number; height: number };

/** The rectangle between two dragged cells, inclusive of both. */
function rectBetween(ax: number, ay: number, bx: number, by: number): Rect {
  return {
    x: Math.min(ax, bx),
    y: Math.min(ay, by),
    width: Math.abs(ax - bx) + 1,
    height: Math.abs(ay - by) + 1,
  };
}

/** One numeric field off an entity's sprite block, with a sane fallback. */
function spriteNum(entity: EntityType | undefined, key: string, fallback = 1): number {
  const raw = Number(entity?.sprite?.[key] ?? fallback);
  return Number.isFinite(raw) && raw > 0 ? raw : fallback;
}

/** An entity's visual scale — how big its art reads against the level, 1 = one cell. */
function spriteScale(entity: EntityType | undefined): number {
  return spriteNum(entity, 'scale');
}

/** Whether the footprint tracks the visual scale. Linked unless deliberately separated. */
function footprintLinked(entity: EntityType | undefined): boolean {
  return entity?.sprite?.footprint_linked !== false;
}

/** A colour per location, stable by index so a box keeps its colour across renders. */
function locationHue(index: number): number {
  return (index * 67) % 360;
}

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
  const [tiles, setTiles] = useState<TileType[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [brush, setBrush] = useState<string>('#');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(true);
  const painting = useRef(false);

  // Two things can be drawn on this grid: tiles, and the boxes that say which place is where.
  // They share the cells but never the same drag, so the mode is explicit rather than modal on
  // which palette entry happens to be selected.
  const [mode, setMode] = useState<'tiles' | 'locations'>('tiles');
  const [locations, setLocations] = useState<Location[]>([]);
  const [activeLocId, setActiveLocId] = useState<number | null>(null);
  const [drag, setDrag] = useState<Rect | null>(null);
  const dragAnchor = useRef<{ x: number; y: number } | null>(null);

  // The scale slider writes to the entity, so it debounces like every other continuous
  // control in the app — dragging a slider must not fire a PATCH per pixel.
  const scaleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    api
      .GET('/api/locations', { params: { query: { level_id: Number(levelId) } } })
      .then(({ data }) => setLocations(data ?? []));
    api
      .GET('/api/tiles', { params: { query: { project_id: Number(projectId) } } })
      .then(({ data }) => setTiles(data ?? []));
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

  /** Save the box just drawn for the active location. */
  async function commitRegion(rect: Rect) {
    const location = locations.find((l) => l.id === activeLocId);
    if (!location) return;
    // A single cell reads as a spot (a well, a door); anything larger is an area. Inferring it
    // from the drag means the creator never has to set the extent before drawing.
    const extent = rect.width === 1 && rect.height === 1 ? 'point' : 'area';
    const { data, error } = await api.PATCH('/api/locations/{location_id}', {
      params: { path: { location_id: location.id } },
      body: { extent, region: rect },
    });
    if (error || !data) return setError((error as { error?: string })?.error ?? 'Failed to place location');
    setError(null);
    setLocations((prev) => prev.map((l) => (l.id === data.id ? data : l)));
  }

  async function clearRegion(location: Location) {
    const { data, error } = await api.PATCH('/api/locations/{location_id}', {
      params: { path: { location_id: location.id } },
      body: { extent: '', region: null },
    });
    if (error || !data) return setError('Failed to unplace location');
    setError(null);
    setLocations((prev) => prev.map((l) => (l.id === data.id ? data : l)));
  }

  /** A cell press: paint a tile, or start dragging a location box. */
  function pressCell(x: number, y: number) {
    if (mode === 'tiles') {
      painting.current = true;
      paint(x, y);
      return;
    }
    if (activeLocId === null) return;
    dragAnchor.current = { x, y };
    setDrag(rectBetween(x, y, x, y));
  }

  function enterCell(x: number, y: number) {
    if (mode === 'tiles') {
      if (painting.current) paint(x, y);
      return;
    }
    const anchor = dragAnchor.current;
    if (anchor) setDrag(rectBetween(anchor.x, anchor.y, x, y));
  }

  function releaseCells() {
    painting.current = false;
    if (dragAnchor.current && drag) void commitRegion(drag);
    dragAnchor.current = null;
    setDrag(null);
  }

  /** Write to the selected entity's sprite block. Optimistic locally, debounced to the API.
   *  The server re-applies the footprint link on save, so a linked footprint can't drift. */
  function setBrushSprite(patch: Record<string, unknown>) {
    const entity = entityByGlyph[brush];
    if (!entity) return;
    const current = {
      scale: spriteScale(entity),
      cells_wide: spriteNum(entity, 'cells_wide'),
      cells_high: spriteNum(entity, 'cells_high'),
      footprint_linked: footprintLinked(entity),
      ...(entity.sprite ?? {}),
    };
    const sprite: Record<string, unknown> = { ...current, ...patch };
    if (sprite.footprint_linked) {
      sprite.cells_wide = sprite.scale;
      sprite.cells_high = sprite.scale;
    }
    setEntities((prev) => prev.map((e) => (e.id === entity.id ? { ...e, sprite } : e)));
    if (scaleTimer.current) clearTimeout(scaleTimer.current);
    scaleTimer.current = setTimeout(() => {
      void api
        .PATCH('/api/entities/{entity_id}', {
          params: { path: { entity_id: entity.id } },
          body: { sprite },
        })
        .then(({ data, error }) => {
          if (error || !data) return setError('Failed to save sprite size');
          // Take the server's normalized block back, so the UI shows what was actually stored.
          setEntities((prev) => prev.map((e) => (e.id === data.id ? data : e)));
        });
    }, 400);
  }

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
  const tileByGlyph = useMemo(() => Object.fromEntries(tiles.map((t) => [t.glyph, t])), [tiles]);

  async function seedTiles() {
    const { data, error } = await api.POST('/api/projects/{project_id}/seed-tiles', {
      params: { path: { project_id: Number(projectId) } },
    });
    if (error || !data) return setError('Failed to add the starter terrain');
    setError(null);
    setTiles(data);
  }

  const cellClass = (ch: string) => {
    if (tileByGlyph[ch]) return 'cell cell--terrain';
    if (ch === '#') return 'cell cell--ground';
    if (ch === '=') return 'cell cell--platform';
    if (ch === 'P') return 'cell cell--player';
    if (ch === 'G') return 'cell cell--goal';
    if (ch === '.') return 'cell';
    const cat = entityByGlyph[ch]?.category;
    return 'cell ' + (cat === 'pickup' ? 'cell--pickup' : cat === 'prop' ? 'cell--prop' : 'cell--enemy');
  };

  return (
    <div className="layout-page" onMouseUp={releaseCells} onMouseLeave={releaseCells}>
      <div className="layout-page__head">
        <div>
          <Link to={`/projects/${projectId}/levels/${levelId}`} className="layout-page__back">
            ← {level?.name ?? 'Level'}
          </Link>
          <h1 className="layout-page__title">Layout</h1>
        </div>
        <div className="layout-page__meta">
          <div className="layout-mode" role="group" aria-label="Edit mode">
            <button
              type="button"
              className={'layout-mode__btn' + (mode === 'tiles' ? ' layout-mode__btn--active' : '')}
              onClick={() => setMode('tiles')}
            >
              Tiles
            </button>
            <button
              type="button"
              className={'layout-mode__btn' + (mode === 'locations' ? ' layout-mode__btn--active' : '')}
              onClick={() => setMode('locations')}
            >
              Locations
            </button>
          </div>
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
          {mode === 'locations' ? (
            <>
              <div className="layout-palette__section">Places</div>
              {locations.length === 0 && (
                <p className="layout-palette__empty">
                  None yet — add some in this level's{' '}
                  <Link to={`/projects/${projectId}/levels/${levelId}/locations`}>Locations</Link>.
                </p>
              )}
              {locations.map((loc, i) => (
                <button
                  key={loc.id}
                  type="button"
                  className={'palette-btn' + (activeLocId === loc.id ? ' palette-btn--active' : '')}
                  onClick={() => setActiveLocId(loc.id)}
                >
                  <span
                    className="palette-btn__swatch"
                    style={{
                      background: `hsl(${locationHue(i)} 70% 55% / 0.55)`,
                      borderColor: `hsl(${locationHue(i)} 70% 60%)`,
                    }}
                  />
                  <span className="layout-place__name">
                    {loc.name}
                    <small className="layout-place__where">
                      {loc.extent === 'level'
                        ? 'whole level'
                        : loc.region
                          ? `${loc.region.width}×${loc.region.height} at (${loc.region.x}, ${loc.region.y})`
                          : 'not placed'}
                    </small>
                  </span>
                </button>
              ))}
              {locations.some((l) => l.region || l.extent === 'level') && (
                <button
                  type="button"
                  className="layout-place__clear"
                  disabled={activeLocId === null}
                  onClick={() => {
                    const loc = locations.find((l) => l.id === activeLocId);
                    if (loc) void clearRegion(loc);
                  }}
                >
                  Unplace selected
                </button>
              )}
            </>
          ) : (
            <>
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
          <div className="layout-palette__section">Terrain</div>
          {tiles.length === 0 && (
            <p className="layout-palette__empty">
              Just solid and one-way so far.{' '}
              <button type="button" className="layout-seed-link" onClick={() => void seedTiles()}>
                Add the standard set
              </button>{' '}
              (ice, lava, spring, ladder, water, checkpoint) — all editable afterwards.
            </p>
          )}
          {tiles.map((t) => (
            <button
              key={t.id}
              type="button"
              className={'palette-btn' + (brush === t.glyph ? ' palette-btn--active' : '')}
              onClick={() => setBrush(t.glyph)}
              title={t.description || undefined}
            >
              <span
                className="palette-btn__swatch"
                style={{ background: t.color || 'var(--bg-1)', borderColor: t.color || 'var(--line)' }}
              >
                {t.glyph}
              </span>
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

          {/* Scale the selected entity's art against the level. Lives here rather than in the
              Entities tab because "does this read too big?" is a question you can only answer
              looking at the level it sits in. */}
          {entityByGlyph[brush] && (
            <div className="layout-scale">
              <label className="layout-scale__label" htmlFor="sprite-scale">
                {entityByGlyph[brush].name} size
                <output className="layout-scale__value">
                  {spriteScale(entityByGlyph[brush]).toFixed(2)}×
                </output>
              </label>
              <input
                id="sprite-scale"
                className="layout-scale__slider"
                type="range"
                min={0.25}
                max={4}
                step={0.05}
                value={spriteScale(entityByGlyph[brush])}
                onChange={(ev) => setBrushSprite({ scale: Number(ev.target.value) })}
              />

              <label className="layout-scale__link">
                <input
                  type="checkbox"
                  checked={footprintLinked(entityByGlyph[brush])}
                  onChange={(ev) => setBrushSprite({ footprint_linked: ev.target.checked })}
                />
                Footprint follows size
              </label>

              {/* Footprint is what the thing *occupies* — collision, level geometry. Linked to
                  the visual size by default, because a hitbox that quietly disagrees with the
                  art is the classic platformer bug. Unlink for a big sprite with a forgiving
                  hitbox. */}
              {!footprintLinked(entityByGlyph[brush]) && (
                <div className="layout-scale__footprint">
                  {(['cells_wide', 'cells_high'] as const).map((key) => (
                    <div key={key} className="layout-scale__row">
                      <label className="layout-scale__label" htmlFor={`fp-${key}`}>
                        {key === 'cells_wide' ? 'Footprint W' : 'Footprint H'}
                        <output className="layout-scale__value">
                          {spriteNum(entityByGlyph[brush], key).toFixed(2)}
                        </output>
                      </label>
                      <input
                        id={`fp-${key}`}
                        className="layout-scale__slider"
                        type="range"
                        min={0.25}
                        max={4}
                        step={0.05}
                        value={spriteNum(entityByGlyph[brush], key)}
                        onChange={(ev) => setBrushSprite({ [key]: Number(ev.target.value) })}
                      />
                    </div>
                  ))}
                </div>
              )}

              <button
                type="button"
                className="layout-scale__reset"
                onClick={() =>
                  setBrushSprite({ scale: 1, footprint_linked: true, cells_wide: 1, cells_high: 1 })
                }
                disabled={
                  spriteScale(entityByGlyph[brush]) === 1 &&
                  footprintLinked(entityByGlyph[brush])
                }
              >
                Reset to one cell
              </button>
            </div>
          )}
            </>
          )}
        </div>

        <div className="layout-grid-wrap">
          <div
            className={'layout-grid' + (mode === 'locations' ? ' layout-grid--locating' : '')}
            style={{ gridTemplateColumns: `repeat(${layout.width}, ${CELL}px)` }}
          >
            {layout.rows.map((row, y) =>
              row.split('').map((ch, x) => (
                <button
                  key={`${x}-${y}`}
                  type="button"
                  className={cellClass(ch)}
                  onMouseDown={() => pressCell(x, y)}
                  onMouseEnter={() => enterCell(x, y)}
                  title={`(${x}, ${y})`}
                >
                  {tileByGlyph[ch] ? (
                    // Custom terrain paints its own greybox colour, the same one the built
                    // game will use, so the editor and the build agree before any art exists.
                    <span
                      className="cell__terrain"
                      style={{ background: tileByGlyph[ch].color || undefined }}
                    >
                      {tileByGlyph[ch].color ? '' : ch}
                    </span>
                  ) : entityByGlyph[ch] ? (
                    // An entity is drawn at its sprite scale so the grid shows how big the
                    // thing actually reads against the level — the marker is allowed to spill
                    // outside its cell, which is the whole point of scaling above 1.
                    <span
                      className="cell__sprite"
                      style={{
                        width: `${spriteScale(entityByGlyph[ch]) * 100}%`,
                        height: `${spriteScale(entityByGlyph[ch]) * 100}%`,
                        backgroundImage: entityByGlyph[ch]?.image_url
                          ? `url(${entityByGlyph[ch].image_url})`
                          : undefined,
                      }}
                    >
                      {entityByGlyph[ch]?.image_url ? '' : ch}
                      {/* When art and hitbox differ, show the footprint so the mismatch is
                          visible while placing rather than discovered in the engine. */}
                      {!footprintLinked(entityByGlyph[ch]) && (
                        <span
                          className="cell__footprint"
                          style={{
                            width: `${(spriteNum(entityByGlyph[ch], 'cells_wide') / spriteScale(entityByGlyph[ch])) * 100}%`,
                            height: `${(spriteNum(entityByGlyph[ch], 'cells_high') / spriteScale(entityByGlyph[ch])) * 100}%`,
                          }}
                        />
                      )}
                    </span>
                  ) : ch !== '.' && ch !== '#' ? (
                    ch
                  ) : (
                    ''
                  )}
                </button>
              )),
            )}

            {/* Placed locations, drawn over the cells they claim. Only in Locations mode, so
                they never obscure tile painting. */}
            {mode === 'locations' &&
              locations.map((loc, i) => {
                const box = loc.extent === 'level'
                  ? { x: 0, y: 0, width: layout.width, height: layout.height }
                  : loc.region;
                if (!box) return null;
                const outside =
                  box.x + box.width > layout.width || box.y + box.height > layout.height;
                return (
                  <div
                    key={loc.id}
                    className={
                      'layout-region' +
                      (activeLocId === loc.id ? ' layout-region--active' : '') +
                      (outside ? ' layout-region--outside' : '')
                    }
                    style={{
                      left: box.x * PITCH,
                      top: box.y * PITCH,
                      width: box.width * PITCH - 1,
                      height: box.height * PITCH - 1,
                      // Hue per location so overlapping places stay tellable apart — nesting
                      // (a well inside a hillside) is expected, not an error.
                      background: `hsl(${locationHue(i)} 70% 55% / 0.22)`,
                      borderColor: `hsl(${locationHue(i)} 70% 62%)`,
                    }}
                  >
                    <span className="layout-region__tag">{loc.name}</span>
                  </div>
                );
              })}

            {/* The box being dragged right now. */}
            {drag && (
              <div
                className="layout-region layout-region--drafting"
                style={{
                  left: drag.x * PITCH,
                  top: drag.y * PITCH,
                  width: drag.width * PITCH - 1,
                  height: drag.height * PITCH - 1,
                }}
              >
                <span className="layout-region__tag">
                  {drag.width}×{drag.height}
                </span>
              </div>
            )}
          </div>
          {mode === 'tiles' ? (
            <p className="layout-page__hint">
              Click or drag to paint with the selected glyph. One cell = one game unit (a 3-unit
              jump clears a 3-cell wall). Paint <strong>P</strong> for the player start and{' '}
              <strong>G</strong> for the goal — each level needs one of each.
            </p>
          ) : (
            <p className="layout-page__hint">
              {activeLocId === null
                ? 'Pick a place on the left, then drag a box on the grid to say where it is.'
                : 'Drag a box to place it. One cell makes it a single spot; a bigger box makes it an area. Places can overlap and nest — a well inside a hillside.'}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
