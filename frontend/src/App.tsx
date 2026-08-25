import { useEffect, useState } from 'react';
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { api, THEMES, type Theme } from './api/client';
import ProjectsPage from './pages/ProjectsPage';
import ProjectHomePage from './pages/ProjectHomePage';
import ProjectSettingsPage from './pages/ProjectSettingsPage';
import ProjectSystemsPage from './pages/ProjectSystemsPage';
import ProjectPreviewPage from './pages/ProjectPreviewPage';
import LevelsPage from './pages/LevelsPage';
import LevelHomePage from './pages/LevelHomePage';
import LevelCharactersPage from './pages/LevelCharactersPage';
import LocationsPage from './pages/LocationsPage';
import ShapeEditorPage from './pages/ShapeEditorPage';
import DialogueEditorPage from './pages/DialogueEditorPage';
import CharactersPage from './pages/CharactersPage';
import CharacterDetailPage from './pages/CharacterDetailPage';
import EntitiesPage from './pages/EntitiesPage';
import LevelLayoutPage from './pages/LevelLayoutPage';

const THEME_LABELS: Record<Theme, string> = {
  neon: 'Neon',
  aqua: 'Aqua',
  light: 'Light',
  studio: 'Studio',
};

function navClass({ isActive }: { isActive: boolean }) {
  return 'app__link' + (isActive ? ' app__link--active' : '');
}

export default function App() {
  const [theme, setTheme] = useState<Theme>('studio');

  // Load the user's saved theme on startup.
  useEffect(() => {
    api.GET('/api/user').then(({ data }) => {
      if (data && (THEMES as readonly string[]).includes(data.theme)) {
        setTheme(data.theme as Theme);
      }
    });
  }, []);

  // Apply the theme to <html> so the whole site (including the body background) updates.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  function cycleTheme() {
    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    setTheme(next); // optimistic
    api.PATCH('/api/user', { body: { theme: next } }); // persist on the user
  }

  return (
    <div className="app">
      <header className="app__nav">
        <Link to="/" className="app__title">
          game-editor
        </Link>
        <nav className="app__links">
          <NavLink to="/" end className={navClass}>
            Projects
          </NavLink>
        </nav>
        <button
          type="button"
          className="app__theme"
          onClick={cycleTheme}
          title="Change theme (saved to your profile)"
        >
          <span className="app__theme-swatch" />
          Theme: {THEME_LABELS[theme]}
        </button>
      </header>
      <main className="app__content">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectHomePage />}>
            <Route index element={<Navigate to="settings" replace />} />
            <Route path="settings" element={<ProjectSettingsPage />} />
            <Route path="systems" element={<ProjectSystemsPage />} />
            <Route path="preview" element={<ProjectPreviewPage />} />
            <Route path="levels" element={<LevelsPage />} />
            <Route path="characters" element={<CharactersPage />} />
            <Route path="entities" element={<EntitiesPage />} />
          </Route>
          <Route path="/projects/:projectId/levels/:levelId" element={<LevelHomePage />} />
          <Route
            path="/projects/:projectId/levels/:levelId/layout"
            element={<LevelLayoutPage />}
          />
          <Route
            path="/projects/:projectId/levels/:levelId/dialogue"
            element={<DialogueEditorPage />}
          />
          <Route
            path="/projects/:projectId/levels/:levelId/characters"
            element={<LevelCharactersPage />}
          />
          <Route
            path="/projects/:projectId/levels/:levelId/locations"
            element={<LocationsPage />}
          />
          <Route
            path="/projects/:projectId/characters/:characterId"
            element={<CharacterDetailPage />}
          />
          <Route path="/shapes" element={<ShapeEditorPage />} />
        </Routes>
      </main>
    </div>
  );
}
