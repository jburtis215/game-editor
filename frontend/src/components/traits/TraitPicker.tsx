import { useState } from 'react';
import {
  TRAIT_CATALOG,
  TRAIT_CATEGORIES,
  TRAIT_TYPES,
  traitKey,
  type TraitDef,
  type TraitType,
} from '../../lib/characterTraits';
import './Traits.css';

type Props = {
  /** Keys already in use — their catalog chips are hidden. */
  taken: string[];
  onAdd: (def: TraitDef) => void;
  /** Copy above the catalog, e.g. what "adding" means on this page. */
  hint?: string;
};

/** Shared "add a trait" UI: pick from the catalog by category, or define a custom one. */
export default function TraitPicker({ taken, onAdd, hint }: Props) {
  const [category, setCategory] = useState<string>(TRAIT_CATEGORIES[0].id);
  const [customOpen, setCustomOpen] = useState(false);
  const [label, setLabel] = useState('');
  const [type, setType] = useState<TraitType>('number');
  const [min, setMin] = useState('0');
  const [max, setMax] = useState('100');

  const takenKeys = new Set(taken);
  const available = TRAIT_CATALOG.filter((t) => t.category === category && !takenKeys.has(t.key));

  function addCustom(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = label.trim();
    if (!trimmed) return;
    const key = traitKey(trimmed);
    if (takenKeys.has(key)) return;
    const lo = Number(min) || 0;
    const hi = Math.max(lo, Number(max) || 100);
    const def: TraitDef =
      type === 'number'
        ? { key, label: trimmed, type, min: lo, max: hi, step: 1, unit: '', default: lo }
        : { key, label: trimmed, type, default: type === 'toggle' ? false : '' };
    onAdd(def);
    setLabel('');
  }

  return (
    <div className="trait-picker">
      {hint && <p className="trait-picker__hint">{hint}</p>}

      <div className="trait-picker__cats">
        {TRAIT_CATEGORIES.map((c) => (
          <button
            key={c.id}
            type="button"
            className={'q-chip' + (category === c.id ? ' q-chip--active' : '')}
            onClick={() => setCategory(c.id)}
          >
            {c.icon} {c.label}
          </button>
        ))}
      </div>

      <div className="trait-picker__options">
        {available.length === 0 ? (
          <span className="trait-picker__empty">Every {category} trait is already added.</span>
        ) : (
          available.map((t) => (
            <button
              key={t.key}
              type="button"
              className="trait-picker__opt"
              onClick={() => onAdd(t)}
              title={`Add ${t.label}`}
            >
              ＋ {t.label}
            </button>
          ))
        )}
      </div>

      {customOpen ? (
        <form className="trait-custom" onSubmit={addCustom}>
          <input
            className="trait-custom__label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Trait name (e.g. Luck)"
            autoFocus
          />
          <select
            className="trait-custom__type"
            value={type}
            onChange={(e) => setType(e.target.value as TraitType)}
          >
            {TRAIT_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          {type === 'number' && (
            <>
              <input
                className="trait-custom__num"
                type="number"
                value={min}
                onChange={(e) => setMin(e.target.value)}
                aria-label="Minimum"
              />
              <span className="trait-custom__dash">–</span>
              <input
                className="trait-custom__num"
                type="number"
                value={max}
                onChange={(e) => setMax(e.target.value)}
                aria-label="Maximum"
              />
            </>
          )}
          <button type="submit" className="btn btn--add" disabled={!label.trim()}>
            ＋ Add
          </button>
          <button type="button" className="trait-custom__cancel" onClick={() => setCustomOpen(false)}>
            ✕
          </button>
        </form>
      ) : (
        <button type="button" className="trait-picker__custom" onClick={() => setCustomOpen(true)}>
          ＋ Custom trait…
        </button>
      )}
    </div>
  );
}
