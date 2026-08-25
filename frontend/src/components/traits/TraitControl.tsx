import type { TraitDef, TraitValue } from '../../lib/characterTraits';
import { coerceValue } from '../../lib/characterTraits';
import './Traits.css';

type Props = {
  def: TraitDef;
  value: TraitValue;
  onChange: (value: TraitValue) => void;
  /** Rendered on the right of the row — remove / reset buttons, badges. */
  actions?: React.ReactNode;
  /** A small tag beside the label (e.g. "default", "custom"). */
  badge?: string;
};

/** One editable trait row. The control shape follows the trait's type. */
export default function TraitControl({ def, value, onChange, actions, badge }: Props) {
  return (
    <div className={'trait-row trait-row--' + def.type}>
      <div className="trait-row__head">
        <span className="trait-row__label">
          {def.label}
          {badge && <span className="trait-row__badge">{badge}</span>}
        </span>
        <div className="trait-row__tail">
          {def.type === 'number' && (
            <span className="trait-row__value">
              {String(value)}
              {def.unit ? ` ${def.unit}` : ''}
            </span>
          )}
          {actions}
        </div>
      </div>

      {def.type === 'number' && (
        <div className="trait-row__number">
          <input
            type="range"
            className="trait-row__slider"
            min={def.min ?? 0}
            max={def.max ?? 100}
            step={def.step ?? 1}
            value={Number(value)}
            onChange={(e) => onChange(coerceValue(def, Number(e.target.value)))}
          />
          <input
            type="number"
            className="trait-row__spin"
            min={def.min ?? 0}
            max={def.max ?? 100}
            step={def.step ?? 1}
            value={Number(value)}
            onChange={(e) => onChange(coerceValue(def, Number(e.target.value)))}
          />
        </div>
      )}

      {def.type === 'text' && (
        <input
          className="trait-row__text"
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={`${def.label}…`}
        />
      )}

      {def.type === 'toggle' && (
        <label className="trait-toggle">
          <input
            type="checkbox"
            className="trait-toggle__input"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span className="trait-toggle__track" aria-hidden="true">
            <span className="trait-toggle__knob" />
          </span>
          <span className="trait-toggle__text">{value ? 'Yes' : 'No'}</span>
        </label>
      )}
    </div>
  );
}
