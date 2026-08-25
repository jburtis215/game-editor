import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BASE_COMPONENTS,
  SYSTEMS,
  buildManifest,
  genreDefaults,
  normalizeSystems,
  type ArchitectState,
  type QuestionDef,
  type Scope,
} from '../lib/gameSystems';
import { api } from '../api/client';
import { useProject } from './ProjectHomePage';
import SystemSim from '../components/systems/SystemSim';
import AbilitiesPanel from '../components/systems/AbilitiesPanel';
import type { StateSchema } from '../api/client';
// The abilities panel reuses the dialogue editor's picker controls (MemoryComboBox et al).
import '../components/dialogue/DialogueEditor.css';
import './ProjectTabs.css';

export default function ProjectSystemsPage() {
  const { project, patchProject } = useProject();
  const [state, setState] = useState<ArchitectState>(() => normalizeSystems(project.systems));
  const [activeId, setActiveId] = useState<string>('health');
  const [copied, setCopied] = useState(false);

  // Debounced persist — skip the initial mount so we don't immediately re-save what we loaded.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const t = setTimeout(() => void patchProject({ systems: state }), 400);
    return () => clearTimeout(t);
  }, [state, patchProject]);

  const activeSystem = SYSTEMS.find((s) => s.id === activeId)!;
  const activeState = state[activeId];

  const toggle = (id: string) =>
    setState((prev) => ({ ...prev, [id]: { ...prev[id], enabled: !prev[id].enabled } }));

  const setValue = (key: string, value: string | string[] | number) =>
    setState((prev) => ({
      ...prev,
      [activeId]: { ...prev[activeId], values: { ...prev[activeId].values, [key]: value } },
    }));

  const gameType = { dimension: project.dimension as '2d' | '3d' | '', genre: project.genre };

  const { foundation, extensions, manifest } = useMemo(() => {
    const foundation: { id: string; components: string[] }[] = [];
    const extensions: { id: string; name: string; components: string[]; scopeNote: string }[] = [];
    for (const sys of SYSTEMS) {
      const st = state[sys.id];
      if (!st?.enabled) continue;
      const scope = (st.values['scope'] as Scope) ?? 'all';
      if (scope === 'all') foundation.push({ id: sys.id, components: sys.components });
      else
        extensions.push({
          id: sys.id,
          name: sys.name,
          components: sys.components,
          scopeNote: scope === 'player' ? 'Player only' : 'Tagged characters',
        });
    }
    return { foundation, extensions, manifest: buildManifest(gameType, state) };
  }, [state, gameType]);

  const enabledCount = Object.values(state).filter((s) => s.enabled).length;

  async function copyManifest() {
    await navigator.clipboard.writeText(JSON.stringify(manifest, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function downloadBlueprint() {
    // The full gameblueprint export (systems + levels + dialogue + characters + entities).
    const { data, error } = await api.GET('/api/projects/{project_id}/export', {
      params: { path: { project_id: project.id } },
    });
    if (error || !data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.name.replace(/[^a-zA-Z0-9_-]+/g, '-').toLowerCase()}-blueprint.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function resetToGenre() {
    setState(genreDefaults(project.genre));
  }

  return (
    <div className="ptab psys">
      <p className="ptab__lead">
        Decide which systems your game has and answer a few questions about each. The blueprint on
        the right is what an AI game maker would build.
      </p>

      <div className="psys__grid">
        <div className="psys__main">
          <section className="ptab__section">
            <div className="ptab__section-head">
              <h2 className="ptab__section-title">Component Catalog</h2>
              <span className="ptab__section-value">
                {enabledCount} / {SYSTEMS.length} enabled
              </span>
            </div>
            <div className="psys__catalog">
              {SYSTEMS.map((sys) => {
                const st = state[sys.id];
                const isActive = sys.id === activeId;
                return (
                  <div
                    key={sys.id}
                    className={
                      'psys-card' +
                      (st.enabled ? ' psys-card--on' : '') +
                      (isActive ? ' psys-card--active' : '')
                    }
                  >
                    <button
                      type="button"
                      className="psys-card__select"
                      onClick={() => setActiveId(sys.id)}
                    >
                      <span className="psys-card__icon">{sys.icon}</span>
                      <span className="psys-card__text">
                        <span className="psys-card__name">{sys.name}</span>
                        <span className="psys-card__blurb">{sys.blurb}</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      aria-label={`Toggle ${sys.name}`}
                      className={'psys-toggle' + (st.enabled ? ' psys-toggle--on' : '')}
                      onClick={() => toggle(sys.id)}
                    >
                      <span className="psys-toggle__knob" />
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="ptab__section psys__config">
            <div className="psys__config-head">
              <h3 className="psys__config-title">{activeSystem.name} Configuration</h3>
              {activeState.enabled && <span className="psys__badge">Active</span>}
            </div>
            {activeState.enabled ? (
              <div className="psys__config-body">
                <div className="psys__questions">
                  {activeSystem.questions.map((q) => (
                    <QuestionRow
                      key={q.key}
                      question={q}
                      value={activeState.values[q.key]}
                      onChange={(v) => setValue(q.key, v)}
                    />
                  ))}
                </div>
                <SystemSim id={activeId} state={state} setValue={setValue} />
              </div>
            ) : (
              <div className="psys__disabled">
                {activeSystem.name} is disabled — toggle it on above to configure.
              </div>
            )}
          </section>
        </div>

        <aside className="psys__blueprint">
          <div className="psys__blueprint-head">
            <h2 className="ptab__section-title">Blueprint</h2>
            <div className="psys__blueprint-actions">
              <button type="button" className="btn" onClick={resetToGenre}>
                Reset
              </button>
              <button type="button" className="btn" onClick={copyManifest}>
                {copied ? 'Copied ✓' : 'Copy'}
              </button>
              <button type="button" className="btn btn--primary" onClick={() => void downloadBlueprint()}>
                Export
              </button>
            </div>
          </div>

          <div className="psys__arch">
            <div className="psys__arch-label">Foundation · BaseCharacter</div>
            {BASE_COMPONENTS.map((b) => (
              <div key={b.name} className="psys__comp psys__comp--base">
                {b.name}
              </div>
            ))}
            {foundation.flatMap((f) =>
              f.components.map((c) => (
                <div key={c} className="psys__comp">
                  {c}
                </div>
              )),
            )}

            <div className="psys__arch-label">Extensions</div>
            {extensions.length === 0 ? (
              <div className="psys__empty">No scoped extensions.</div>
            ) : (
              extensions.map((e) => (
                <div key={e.id} className="psys__ext">
                  <span className="psys__ext-name">{e.name}Extension</span>
                  <span className="psys__ext-scope">{e.scopeNote}</span>
                </div>
              ))
            )}
          </div>

          <pre className="psys__manifest">{JSON.stringify(manifest, null, 2)}</pre>
        </aside>
      </div>

      {/* The verb set sits below the architect: project-wide data, not one system's answers. */}
      <AbilitiesPanel
        projectId={project.id}
        stateSchema={(project.state_schema ?? {}) as StateSchema}
      />
    </div>
  );
}

function QuestionRow({
  question,
  value,
  onChange,
}: {
  question: QuestionDef;
  value: string | string[] | number;
  onChange: (v: string | string[] | number) => void;
}) {
  if (question.kind === 'single') {
    const v = value as string;
    return (
      <div className="q">
        <label className="q__label">{question.label}</label>
        <div className="q__options">
          {question.options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={'q-opt' + (opt.id === v ? ' q-opt--active' : '')}
              onClick={() => onChange(opt.id)}
            >
              <span className="q-opt__label">{opt.label}</span>
              {opt.description && <span className="q-opt__desc">{opt.description}</span>}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (question.kind === 'multi') {
    const v = value as string[];
    return (
      <div className="q">
        <label className="q__label">{question.label}</label>
        <div className="q__chips">
          {question.options.map((opt) => {
            const active = v.includes(opt.id);
            return (
              <button
                key={opt.id}
                type="button"
                className={'q-chip' + (active ? ' q-chip--active' : '')}
                onClick={() =>
                  onChange(active ? v.filter((x) => x !== opt.id) : [...v, opt.id])
                }
              >
                {active ? '✓ ' : ''}
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  const v = value as number;
  return (
    <div className="q">
      <div className="q__slider-head">
        <label className="q__label">{question.label}</label>
        <span className="q__slider-value">
          {v} {question.unit}
        </span>
      </div>
      <input
        type="range"
        className="q__slider"
        min={question.min}
        max={question.max}
        step={question.step}
        value={v}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
