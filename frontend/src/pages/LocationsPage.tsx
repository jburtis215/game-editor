import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  api,
  type Character,
  type Level,
  type Location,
  type Scene,
  type StateSchema,
} from '../api/client';
import LocationCard from '../components/locations/LocationCard';
// The connection's "locked until…" picker reuses the dialogue editor's requirement controls
// (MemoryComboBox + the effects row), so it borrows their styles too.
import '../components/dialogue/DialogueEditor.css';
import './Locations.css';

export default function LocationsPage() {
  const { projectId, levelId } = useParams();
  const navigate = useNavigate();
  const [level, setLevel] = useState<Level | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  // The project's story state — what a connection's requirement may reference.
  const [stateSchema, setStateSchema] = useState<StateSchema>({});
  const [error, setError] = useState<string | null>(null);

  /** (Re)load the level's locations — used on mount and whenever a connection changes,
   * since one connection shows on both of the locations it joins. */
  const loadLocations = useCallback(() => {
    if (!levelId) return;
    void api
      .GET('/api/locations', { params: { query: { level_id: Number(levelId) } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load locations');
        setError(null);
        setLocations(data);
      });
  }, [levelId]);

  useEffect(() => {
    if (!levelId) return;
    const id = Number(levelId);
    api
      .GET('/api/levels/{level_id}', { params: { path: { level_id: id } } })
      .then(({ data }) => data && setLevel(data));
    loadLocations();
    api.GET('/api/scenes').then(({ data }) => {
      if (data) setScenes(data.filter((s) => String(s.level_id) === levelId));
    });
  }, [levelId, loadLocations]);

  // Project characters power the "place a character here" dropdown; the project's state
  // schema powers the connection requirement picker. This page is outside the project tab
  // layout, so there's no useProject() — fetch what we need directly.
  useEffect(() => {
    if (!projectId) return;
    const project_id = Number(projectId);
    api
      .GET('/api/characters', { params: { query: { project_id } } })
      .then(({ data }) => data && setCharacters(data));
    api
      .GET('/api/projects/{project_id}', { params: { path: { project_id } } })
      .then(({ data }) => data && setStateSchema((data.state_schema ?? {}) as StateSchema));
  }, [projectId]);

  const replaceLocation = useCallback((loc: Location) => {
    setLocations((prev) => prev.map((l) => (l.id === loc.id ? loc : l)));
  }, []);

  async function addLocation() {
    const { data, error } = await api.POST('/api/locations', {
      body: { name: 'New Location', description: '', level_id: levelId ? Number(levelId) : null },
    });
    if (error || !data) return setError('Failed to add location');
    setError(null);
    setLocations((prev) => [...prev, data]);
  }

  async function deleteLocation(id: number) {
    const { error } = await api.DELETE('/api/locations/{location_id}', {
      params: { path: { location_id: id } },
    });
    if (error) return setError('Failed to delete location');
    setError(null);
    setLocations((prev) => prev.filter((l) => l.id !== id));
    loadLocations(); // its connections went with it — refresh the cards at the far ends
  }

  async function addScene(locationId: number) {
    if (!levelId) return;
    const { data, error } = await api.POST('/api/scenes', {
      body: { name: 'New Scene', level_id: Number(levelId), location_id: locationId },
    });
    if (error || !data) return setError('Failed to add scene');
    setError(null);
    setScenes((prev) => [...prev, data]);
  }

  const dialogueHref = `/projects/${projectId}/levels/${levelId}/dialogue`;

  return (
    <div className="locations-page">
      <Link to={`/projects/${projectId}/levels/${levelId}`} className="locations-page__back">
        ← {level?.name ?? 'Level'}
      </Link>
      <div className="locations-page__head">
        <h1 className="locations-page__title">Locations</h1>
        <button type="button" className="btn btn--add" onClick={addLocation}>
          ＋ New location
        </button>
      </div>
      <p className="locations-page__lead">
        Places within this level. Describe what each one is like, say who's present, connect them
        into a map, and create the scenes that happen there.
      </p>
      {error && <p className="locations-page__error">{error}</p>}
      {!error && locations.length === 0 && (
        <p className="locations-page__empty">No locations yet — add your first.</p>
      )}

      <div className="locations-page__list">
        {locations.map((loc) => (
          <LocationCard
            key={loc.id}
            location={loc}
            projectId={projectId ?? ''}
            levelId={levelId ?? ''}
            characters={characters}
            siblings={locations.filter((l) => l.id !== loc.id)}
            scenes={scenes.filter((s) => s.location_id === loc.id)}
            stateSchema={stateSchema}
            onReplace={replaceLocation}
            onConnectionsChanged={loadLocations}
            onDelete={deleteLocation}
            onAddScene={addScene}
            onOpenScene={() => navigate(dialogueHref)}
            onError={setError}
          />
        ))}
      </div>
    </div>
  );
}
