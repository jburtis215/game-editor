import { useCallback, useEffect, useState } from 'react';
import { api, type Ability, type StateSchema } from '../../api/client';
import AbilityCard from './AbilityCard';

interface AbilitiesPanelProps {
  projectId: number;
  /** The project's story state — what an ability's unlock requirement may reference. */
  stateSchema: StateSchema;
}

/**
 * The project's verb set. Systems tune numbers; this is the list of actions those numbers
 * apply to — per-project data rather than questionnaire answers, so it owns its own rows.
 */
export default function AbilitiesPanel({ projectId, stateSchema }: AbilitiesPanelProps) {
  const [abilities, setAbilities] = useState<Ability[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data, error } = await api.GET('/api/abilities', {
      params: { query: { project_id: projectId } },
    });
    if (error || !data) return setError('Failed to load abilities');
    setError(null);
    setAbilities(data);
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function addAbility() {
    const { data, error } = await api.POST('/api/abilities', {
      body: {
        project_id: projectId,
        name: 'New Ability',
        description: '',
        params: {},
        unlock_requirements: [],
      },
    });
    if (error || !data) return setError('Failed to create ability');
    setError(null);
    setAbilities((prev) => [...prev, data]);
  }

  async function deleteAbility(id: number) {
    const { error } = await api.DELETE('/api/abilities/{ability_id}', {
      params: { path: { ability_id: id } },
    });
    if (error) return setError('Failed to delete ability');
    setError(null);
    setAbilities((prev) => prev.filter((a) => a.id !== id));
  }

  return (
    <section className="ptab__section pab">
      <div className="ptab__section-head">
        <h2 className="ptab__section-title">Abilities</h2>
        <span className="ptab__section-value">{abilities.length} verbs</span>
      </div>
      <p className="pab__lead">
        What can the player actually <em>do</em>? Systems tune the numbers; these are the actions
        they apply to. Leave the unlock empty for something the player starts with.
      </p>

      {error && <p className="pab__error">{error}</p>}

      <div className="pab__list">
        {abilities.length === 0 && (
          <p className="pab__empty">No abilities yet — every game needs at least one verb.</p>
        )}
        {abilities.map((ability) => (
          <AbilityCard
            key={ability.id}
            ability={ability}
            stateSchema={stateSchema}
            onDelete={(id) => void deleteAbility(id)}
            onError={setError}
          />
        ))}
      </div>

      <button type="button" className="btn btn--add" onClick={() => void addAbility()}>
        ＋ New ability
      </button>
    </section>
  );
}
