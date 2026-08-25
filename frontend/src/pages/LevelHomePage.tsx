import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type Level } from '../api/client';
import './LevelHome.css';

export default function LevelHomePage() {
  const { projectId, levelId } = useParams();
  const [level, setLevel] = useState<Level | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!levelId) return;
    api
      .GET('/api/levels/{level_id}', { params: { path: { level_id: Number(levelId) } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load level');
        setError(null);
        setLevel(data);
      });
  }, [levelId]);

  return (
    <div className="level-home">
      <Link to={`/projects/${projectId}`} className="level-home__back">
        ← Project
      </Link>
      <h1 className="level-home__title">{level?.name ?? 'Level'}</h1>
      {error && <p className="level-home__error">{error}</p>}

      <div className="level-home__tiles">
        <Link to={`/projects/${projectId}/levels/${levelId}/layout`} className="lh-tile">
          <span className="lh-tile__icon">🗺️</span>
          <span className="lh-tile__title">Layout</span>
          <span className="lh-tile__desc">Paint the level's tile map</span>
        </Link>

        <Link to={`/projects/${projectId}/levels/${levelId}/dialogue`} className="lh-tile">
          <span className="lh-tile__icon">💬</span>
          <span className="lh-tile__title">Dialogue</span>
          <span className="lh-tile__desc">Scenes & branching dialogue</span>
        </Link>

        <Link to={`/projects/${projectId}/levels/${levelId}/characters`} className="lh-tile">
          <span className="lh-tile__icon">🎭</span>
          <span className="lh-tile__title">Characters</span>
          <span className="lh-tile__desc">Cast &amp; their dialogue</span>
        </Link>

        <Link to={`/projects/${projectId}/levels/${levelId}/locations`} className="lh-tile">
          <span className="lh-tile__icon">📍</span>
          <span className="lh-tile__title">Locations</span>
          <span className="lh-tile__desc">Places, who's there &amp; scenes</span>
        </Link>

        <div className="lh-tile lh-tile--soon" aria-disabled="true">
          <span className="lh-tile__icon">⚙️</span>
          <span className="lh-tile__title">Settings</span>
          <span className="lh-tile__desc">Coming soon</span>
        </div>
      </div>
    </div>
  );
}
