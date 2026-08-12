import { useEffect, useRef, useState } from 'react';
import { DIMENSIONS, GENRES, genreDefaults, type Dimension } from '../lib/gameSystems';
import {
  normalizeTraitDefs,
  type TraitDef,
  type TraitValue,
} from '../lib/characterTraits';
import TraitControl from '../components/traits/TraitControl';
import TraitPicker from '../components/traits/TraitPicker';
import { useProject } from './ProjectHomePage';
import './ProjectTabs.css';

export default function ProjectSettingsPage() {
  const { project, patchProject } = useProject();

  // Default character traits. Dimension/genre write through on click because clicks are discrete,
  // but the trait sliders below are continuous — so keep a local working copy and debounce.
  const [traits, setTraits] = useState<TraitDef[]>(() =>
    normalizeTraitDefs(project.character_traits),
  );
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const t = setTimeout(() => void patchProject({ character_traits: traits }), 400);
    return () => clearTimeout(t);
  }, [traits, patchProject]);

  function pickDimension(dimension: Dimension) {
    void patchProject({ dimension: project.dimension === dimension ? '' : dimension });
  }

  function pickGenre(genre: string) {
    if (project.genre === genre) return;
    // Seed sensible system defaults from the genre, but only if the user hasn't
    // configured systems yet — never clobber existing work.
    const systemsEmpty = !project.systems || Object.keys(project.systems).length === 0;
    void patchProject(systemsEmpty ? { genre, systems: genreDefaults(genre) } : { genre });
  }

  function setTraitDefault(key: string, value: TraitValue) {
    setTraits((prev) => prev.map((t) => (t.key === key ? { ...t, default: value } : t)));
  }

  return (
    <div className="ptab pset">
      <p className="ptab__lead">
        Pick a dimension and a genre. These decide which systems and questions make sense for your
        game — choosing a genre also pre-enables a sensible starter set of systems.
      </p>

      <section className="ptab__section">
        <div className="ptab__section-head">
          <h2 className="ptab__section-title">Dimension</h2>
          <span className="ptab__section-value">
            {project.dimension ? project.dimension.toUpperCase() : '—'}
          </span>
        </div>
        <div className="pset__dims">
          {DIMENSIONS.map((d) => (
            <button
              key={d.id}
              type="button"
              className={'pset-card' + (project.dimension === d.id ? ' pset-card--active' : '')}
              onClick={() => pickDimension(d.id)}
            >
              <span className="pset-card__icon">{d.icon}</span>
              <span className="pset-card__body">
                <span className="pset-card__label">{d.label}</span>
                <span className="pset-card__blurb">{d.blurb}</span>
              </span>
              {project.dimension === d.id && <span className="pset-card__check">✓</span>}
            </button>
          ))}
        </div>
      </section>

      <section className="ptab__section">
        <div className="ptab__section-head">
          <h2 className="ptab__section-title">Genre</h2>
          <span className="ptab__section-value">
            {project.genre ? project.genre.toUpperCase() : '—'}
          </span>
        </div>
        <div className="pset__genres">
          {GENRES.map((g) => (
            <button
              key={g.id}
              type="button"
              className={'pset-card' + (project.genre === g.id ? ' pset-card--active' : '')}
              onClick={() => pickGenre(g.id)}
            >
              <span className="pset-card__icon">{g.icon}</span>
              <span className="pset-card__body">
                <span className="pset-card__label">{g.name}</span>
                <span className="pset-card__blurb">{g.blurb}</span>
              </span>
              {project.genre === g.id && <span className="pset-card__check">✓</span>}
            </button>
          ))}
        </div>
      </section>

      <section className="ptab__section">
        <div className="ptab__section-head">
          <h2 className="ptab__section-title">Default character traits</h2>
          <span className="ptab__section-value">
            {traits.length ? `${traits.length} trait${traits.length === 1 ? '' : 's'}` : '—'}
          </span>
        </div>
        <p className="ptab__lead">
          Every character in this project gets these traits, starting at the value you set here.
          Individual characters can override a value or add traits of their own.
        </p>

        {traits.length > 0 && (
          <div className="trait-list">
            {traits.map((def) => (
              <TraitControl
                key={def.key}
                def={def}
                value={def.default}
                onChange={(v) => setTraitDefault(def.key, v)}
                actions={
                  <button
                    type="button"
                    className="trait-row__action"
                    aria-label={`Remove ${def.label}`}
                    title="Remove from every character"
                    onClick={() => setTraits((prev) => prev.filter((t) => t.key !== def.key))}
                  >
                    ✕
                  </button>
                }
              />
            ))}
          </div>
        )}

        <TraitPicker
          taken={traits.map((t) => t.key)}
          hint="Add a trait every character should have. Removing one here removes it from every character."
          onAdd={(def) => setTraits((prev) => (prev.some((t) => t.key === def.key) ? prev : [...prev, def]))}
        />
      </section>
    </div>
  );
}
