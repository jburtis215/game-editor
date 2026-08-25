import { useCallback, useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom';
import { api, type Project } from '../api/client';
import './ProjectHome.css';

/** Shared context the project tabs use to read/update the current project. */
export type ProjectContext = {
  project: Project;
  /** Persist a partial update to the project and reflect it locally. */
  patchProject: (patch: Partial<Project>) => Promise<void>;
};

export function useProject() {
  return useOutletContext<ProjectContext>();
}

const TABS = [
  { to: 'settings', label: 'Settings' },
  { to: 'systems', label: 'Systems' },
  { to: 'levels', label: 'Levels' },
  { to: 'characters', label: 'Characters' },
  { to: 'entities', label: 'Entities' },
  { to: 'preview', label: 'Preview' },
] as const;

function tabClass({ isActive }: { isActive: boolean }) {
  return 'project-tab' + (isActive ? ' project-tab--active' : '');
}

export default function ProjectHomePage() {
  const { projectId } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api
      .GET('/api/projects/{project_id}', { params: { path: { project_id: Number(projectId) } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load project');
        setError(null);
        setProject(data);
      });
  }, [projectId]);

  const patchProject = useCallback(
    async (patch: Partial<Project>) => {
      if (!projectId) return;
      // Optimistic local update so tabs feel instant.
      setProject((prev) => (prev ? { ...prev, ...patch } : prev));
      const { data, error } = await api.PATCH('/api/projects/{project_id}', {
        params: { path: { project_id: Number(projectId) } },
        body: patch,
      });
      if (error || !data) return setError('Failed to save project');
      setError(null);
      setProject(data);
    },
    [projectId],
  );

  return (
    <div className="project-home">
      <div className="project-home__bar">
        <div className="project-home__heading">
          <Link to="/" className="project-home__back">
            ← Projects
          </Link>
          <h1 className="project-home__title">{project?.name ?? 'Project'}</h1>
        </div>
        <nav className="project-tabs">
          {TABS.map((tab) => (
            <NavLink key={tab.to} to={tab.to} className={tabClass}>
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>

      {error && <p className="project-home__error">{error}</p>}

      <div className="project-home__content">
        {project ? <Outlet context={{ project, patchProject } satisfies ProjectContext} /> : null}
      </div>
    </div>
  );
}
