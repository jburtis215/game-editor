import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  api,
  type Character,
  type DialogueDetail,
  type DialogueEffect,
  type DialogueNode,
  type DialogueRequirement,
  type Project,
  type Scene,
  type StateSchema,
} from '../api/client';
import { ScenesSidebar } from '../components/dialogue/ScenesSidebar';
import { CharactersSidebar } from '../components/dialogue/CharactersSidebar';
import { DialogueBlob } from '../components/dialogue/DialogueBlob';
import { DialogueForm } from '../components/dialogue/DialogueForm';
import { ResponseWheel } from '../components/dialogue/ResponseWheel';
import { DialogueTree } from '../components/dialogue/DialogueTree';
import { MemoryComboBox } from '../components/dialogue/MemoryComboBox';
import '../components/dialogue/DialogueEditor.css';


type ViewMode = 'focus' | 'tree';

function getStateEntriesForRequirement(
  stateSchema: StateSchema,
  requirementType: 'remembered_choice' | 'has_item' | 'stat_check' | 'flag',
) {
  const stateType =
    requirementType === 'has_item'
      ? 'item'
      : requirementType === 'stat_check'
        ? 'stat'
        : requirementType === 'remembered_choice'
          ? 'remembered_choice'
          : 'flag';

  return Object.values(stateSchema).filter((entry) => entry.type === stateType);
}

function getRequirementLabel(requirement: DialogueRequirement, stateSchema: StateSchema) {
  const entry = stateSchema[requirement.state_key];
  const label = entry?.label ?? requirement.state_key;

  if (requirement.type === 'has_item') return `Requires item: ${label}`;

  if (requirement.type === 'stat_check') {
    const opLabel =
      requirement.op === 'at_least'
        ? 'at least'
        : requirement.op === 'less_than'
          ? 'less than'
          : 'equal to';
    return `Requires stat: ${label} ${opLabel} ${requirement.value}`;
  }

  if (entry?.type === 'remembered_choice') return `Requires choice: ${label}`;
  return `Requires: ${label} = ${requirement.value === true ? 'Yes' : String(requirement.value)}`;
}

export default function DialogueEditorPage() {
  const { projectId, levelId } = useParams();
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [sceneId, setSceneId] = useState<number | null>(null);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DialogueDetail | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [adding, setAdding] = useState(false);
  const [addRequirements, setAddRequirements] = useState<DialogueRequirement[]>([]);
  const [addRequirementType, setAddRequirementType] = useState<
    'remembered_choice' | 'has_item' | 'stat_check' | 'flag'
  >('remembered_choice');
  const [addRequirementStateKey, setAddRequirementStateKey] = useState('');
  const [addRequirementStatOp, setAddRequirementStatOp] = useState<
    'at_least' | 'less_than' | 'equals'
  >('at_least');
  const [addRequirementValue, setAddRequirementValue] = useState(1);
  const [addRequirementFlagValue, setAddRequirementFlagValue] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('focus');
  const [treeNodes, setTreeNodes] = useState<DialogueNode[]>([]);
  const [importingYarn, setImportingYarn] = useState(false);
  const [yarnText, setYarnText] = useState('');
  const [yarnWarnings, setYarnWarnings] = useState<string[]>([]);
  const [yarnError, setYarnError] = useState<string | null>(null);
  const [attachYarnToCurrent, setAttachYarnToCurrent] = useState(true);
  const [exportingYarn, setExportingYarn] = useState(false);
  const [exportFilename, setExportFilename] = useState('');
  const [exportText, setExportText] = useState('');
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportCopied, setExportCopied] = useState(false);
  // "Merge" flow: point the current node at an existing node as an additional response,
  // so multiple branches can converge back onto the same dialogue.
  const [linking, setLinking] = useState(false);
  const [linkCandidates, setLinkCandidates] = useState<DialogueNode[]>([]);
  const [linkTargetId, setLinkTargetId] = useState<number | null>(null);
  const [linkOptionLabel, setLinkOptionLabel] = useState('');

  // Load project-level game memory, including remembered choices/items/stats/flags.
  useEffect(() => {
    if (!projectId) return;
    api.GET('/api/projects/{project_id}', {
      params: { path: { project_id: Number(projectId) } },
    }).then(({ data, error }) => {
      if (error || !data) return setError('Failed to load project');
      setError(null);
      setProject(data);
    });
  }, [projectId]);

  // Characters power both the right sidebar and the form dropdowns (scoped to this project).
  useEffect(() => {
    const query = projectId ? { project_id: Number(projectId) } : undefined;
    api.GET('/api/characters', { params: { query } }).then(({ data }) => data && setCharacters(data));
  }, [projectId]);

  // Load this level's scenes and select the first one.
  useEffect(() => {
    api.GET('/api/scenes').then(({ data, error }) => {
      if (error || !data) return setError('Failed to load scenes');
      const levelScenes = levelId
        ? data.filter((s) => String(s.level_id) === levelId)
        : data;
      setError(null);
      setScenes(levelScenes);
      setSceneId(levelScenes[0]?.id ?? null);
    });
  }, [levelId]);

  // When the scene changes, load that scene's root dialogue (the page is scoped to a scene).
  useEffect(() => {
    if (sceneId == null) return;
    setAdding(false);
    setAddRequirements([]);
    api
      .GET('/api/dialogues', { params: { query: { scene_id: sceneId } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load dialogues');
        setError(null);
        setCurrentId(data[0]?.id ?? null); // null => empty scene
      });
  }, [sceneId]);

  const loadDialogue = useCallback((id: number) => {
    return api
      .GET('/api/dialogues/{dialogue_id}', { params: { path: { dialogue_id: id } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load dialogue');
        setError(null);
        setDetail(data);
      });
  }, []);

  // Load the focused dialogue (or clear it for an empty scene).
  useEffect(() => {
    if (currentId == null) {
      setDetail(null);
      return;
    }
    loadDialogue(currentId);
  }, [currentId, loadDialogue]);

  // The whole scene's tree (flat) — powers the Tree view. Reloads when the scene changes.
  const loadTree = useCallback(() => {
    if (sceneId == null) return Promise.resolve();
    return api
      .GET('/api/scenes/{scene_id}/dialogues', { params: { path: { scene_id: sceneId } } })
      .then(({ data, error }) => {
        if (error || !data) return setError('Failed to load dialogue tree');
        setError(null);
        setTreeNodes(data);
      });
  }, [sceneId]);

  useEffect(() => {
    if (viewMode === 'tree') loadTree();
  }, [viewMode, loadTree]);

  async function saveStateSchema(next: StateSchema) {
    if (!projectId || !project) return;
    const { data, error } = await api.PATCH('/api/projects/{project_id}', {
      params: { path: { project_id: Number(projectId) } },
      body: { state_schema: next },
    });
    if (error || !data) {
      setError('Failed to save game memory');
      return;
    }
    setError(null);
    setProject(data);
  }

  async function handleEdit(
    text: string,
    characterId: number | null,
    requirements?: DialogueRequirement[],
    effects?: DialogueEffect[],
    nextStateSchema?: StateSchema,
  ) {
    if (currentId == null) return;
    const { data, error } = await api.PATCH('/api/dialogues/{dialogue_id}', {
      params: { path: { dialogue_id: currentId } },
      body: { text, character_id: characterId, requirements, effects },
    });
    if (error || !data) return setError('Failed to save dialogue');
    setError(null);
    setDetail(data);
    if (nextStateSchema) await saveStateSchema(nextStateSchema);
    if (viewMode === 'tree') loadTree(); // keep the graph in sync
  }

  // Create a brand-new character (e.g. to write dialogue for someone not yet in the cast).
  async function createCharacter(name: string): Promise<Character | null> {
    if (!projectId) return null;
    const { data, error } = await api.POST('/api/characters', {
      body: { name, description: '', project_id: Number(projectId) },
    });
    if (error || !data) {
      setError('Failed to create character');
      return null;
    }
    setError(null);
    setCharacters((prev) => [...prev, data]);
    return data;
  }

  function resetAddRequirementDraft() {
    setAddRequirements([]);
    setAddRequirementType('remembered_choice');
    setAddRequirementStateKey('');
    setAddRequirementStatOp('at_least');
    setAddRequirementValue(1);
    setAddRequirementFlagValue(true);
  }

  function handleAddRequirement() {
    if (!addRequirementStateKey) return;

    let nextRequirement: DialogueRequirement;
    if (addRequirementType === 'has_item') {
      nextRequirement = { type: 'has_item', state_key: addRequirementStateKey };
    } else if (addRequirementType === 'stat_check') {
      nextRequirement = {
        type: 'stat_check',
        state_key: addRequirementStateKey,
        op: addRequirementStatOp,
        value: addRequirementValue,
      };
    } else {
      nextRequirement = {
        type: 'state_equals',
        state_key: addRequirementStateKey,
        value: addRequirementFlagValue,
      };
    }

    setAddRequirements((current) => [...current, nextRequirement]);
    setAddRequirementStateKey('');
  }

  function handleRemoveAddRequirement(indexToRemove: number) {
    setAddRequirements((current) => current.filter((_, index) => index !== indexToRemove));
  }

  // Create a new (empty) scene in this level and switch to it.
  async function createScene() {
    if (!levelId) return;
    const { data, error } = await api.POST('/api/scenes', {
      body: { name: 'New Scene', level_id: Number(levelId) },
    });
    if (error || !data) return setError('Failed to create scene');
    setError(null);
    setScenes((prev) => [...prev, data]);
    setSceneId(data.id);
  }

  async function handleAdd(text: string, characterId: number | null) {
    if (sceneId == null) return;
    const { data, error } = await api.POST('/api/dialogues', {
      body: {
        scene_id: sceneId,
        parent_id: currentId,
        character_id: characterId,
        text,
        requirements: addRequirements,
        effects: [],
      },
    });
    if (error || !data) return setError('Failed to add dialogue');
    setError(null);
    setAdding(false);
    resetAddRequirementDraft();
    if (currentId == null) setCurrentId(data.id); // created this scene's first (root) node
    else await loadDialogue(currentId); // refresh so the new response shows in the wheel
    if (viewMode === 'tree') loadTree(); // reflect the new node/edge in the graph
  }

  // Open the merge picker: load the scene's other nodes so the current node can converge onto
  // one that already exists (multiple branches → the same response, no new node).
  async function openLinkPicker() {
    if (sceneId == null || currentId == null) return;
    setAdding(false);
    const { data, error } = await api.GET('/api/scenes/{scene_id}/dialogues', {
      params: { path: { scene_id: sceneId } },
    });
    if (error || !data) return setError('Failed to load scene nodes');
    setError(null);
    setLinkCandidates(data);
    setLinkTargetId(null);
    setLinkOptionLabel('');
    setLinking(true);
  }

  // Attach an existing node as an additional response of the current one (a convergence edge).
  async function handleLink() {
    if (currentId == null || linkTargetId == null) return;
    const { data, error } = await api.POST('/api/dialogues/{dialogue_id}/link', {
      params: { path: { dialogue_id: currentId } },
      body: { target_id: linkTargetId, option_label: linkOptionLabel },
    });
    if (error || !data) return setError('Failed to link response');
    setError(null);
    setDetail(data);
    setLinking(false);
    if (viewMode === 'tree') loadTree(); // show the new converging edge in the graph
  }

  async function handleImportYarn() {
    if (sceneId == null || !yarnText.trim()) return;
    const attachTo = attachYarnToCurrent && currentId != null ? currentId : undefined;
    const { data, error } = await api.POST('/api/scenes/{scene_id}/import-yarn', {
      params: { path: { scene_id: sceneId } },
      body: { text: yarnText, parent_id: attachTo },
    });
    if (error || !data) {
      setYarnError((error as { error?: string })?.error ?? 'Import failed');
      setYarnWarnings([]);
      return;
    }
    setYarnError(null);
    setYarnWarnings(data.warnings);
    setYarnText('');

    if (attachTo != null) {
      await loadDialogue(attachTo); // refresh the wheel so the new response(s) show up
    } else {
      const roots = await api.GET('/api/dialogues', { params: { query: { scene_id: sceneId } } });
      const rootDialogues = roots.data ?? [];
      const preferred = data.root_ids.find((id) => rootDialogues.some((r) => r.id === id));
      setCurrentId(preferred ?? rootDialogues[0]?.id ?? null);
    }
    if (viewMode === 'tree') loadTree();
  }

  async function handleExportYarn() {
    if (sceneId == null) return;
    setImportingYarn(false);
    setExportingYarn(true);
    setExportCopied(false);
    const { data, error } = await api.GET('/api/scenes/{scene_id}/export-yarn', {
      params: { path: { scene_id: sceneId } },
    });
    if (error || !data) {
      setExportError('Export failed');
      setExportText('');
      return;
    }
    setExportError(null);
    setExportFilename(data.filename);
    setExportText(data.text);
  }

  function handleCopyExport() {
    navigator.clipboard
      .writeText(exportText)
      .then(() => {
        setExportCopied(true);
        setTimeout(() => setExportCopied(false), 1500);
      })
      .catch(() => setExportError('Copy failed — use Download instead'));
  }

  function handleDownloadExport() {
    const blob = new Blob([exportText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = exportFilename || 'scene.yarn';
    link.click();
    URL.revokeObjectURL(url);
  }

  const selectedScene = scenes.find((s) => s.id === sceneId) ?? null;
  const addLabel = currentId == null ? '＋ Add dialogue' : '＋ Add response';
  // Nodes the current one can merge into: any other node not already one of its responses.
  const linkableCandidates = linkCandidates.filter(
    (node) => node.id !== currentId && !(detail?.responses ?? []).some((r) => r.id === node.id),
  );

  return (
    <div className="dialogue-editor">
      <ScenesSidebar
        scenes={scenes}
        selectedId={sceneId}
        onSelect={setSceneId}
        onCreateScene={createScene}
      />

      <section className="dialogue-editor__stage">
        <div className="dialogue-editor__crumb">
          <Link
            to={`/projects/${projectId}/levels/${levelId}`}
            className="dialogue-editor__back-link"
          >
            ← Level
          </Link>
        </div>

        {selectedScene && (
          <div className="dialogue-editor__scene-title">
            {selectedScene.level_name} · {selectedScene.name}
          </div>
        )}

        {sceneId != null && (
          <div className="dialogue-editor__toolbar">
            <div className="dialogue-editor__viewtoggle">
              <button
                type="button"
                className={`dialogue-editor__viewbtn${viewMode === 'focus' ? ' is-active' : ''}`}
                onClick={() => setViewMode('focus')}
              >
                Focus
              </button>
              <button
                type="button"
                className={`dialogue-editor__viewbtn${viewMode === 'tree' ? ' is-active' : ''}`}
                onClick={() => setViewMode('tree')}
              >
                Tree
              </button>
            </div>
            <button
              type="button"
              className="dialogue-editor__back"
              onClick={() => {
                setImportingYarn((prev) => !prev);
                setExportingYarn(false);
                setYarnError(null);
                setYarnWarnings([]);
              }}
            >
              {importingYarn ? 'Close Yarn import' : 'Import Yarn'}
            </button>
            <button
              type="button"
              className="dialogue-editor__back"
              onClick={() => (exportingYarn ? setExportingYarn(false) : handleExportYarn())}
            >
              {exportingYarn ? 'Close Yarn export' : 'Export Yarn'}
            </button>
          </div>
        )}

        {exportingYarn && sceneId != null && (
          <div className="yarn-import">
            <div className="yarn-import__header">
              This scene's dialogue graph as a Yarn script — straight lines are merged into one
              node; branches and shared nodes get their own <code>title:</code> and a real{' '}
              <code>&lt;&lt;jump&gt;&gt;</code>. Variable <code>&lt;&lt;declare&gt;&gt;</code>{' '}
              headers aren't included (to avoid duplicate declarations across multiple exported
              scenes) — add them once yourself if your Yarn Spinner setup requires them.
            </div>
            {exportError && <p className="dialogue-editor__error">{exportError}</p>}
            {!exportError && (
              <>
                <textarea className="yarn-import__text" value={exportText} readOnly rows={14} />
                <div className="yarn-import__actions">
                  <button type="button" className="btn btn--primary" onClick={handleDownloadExport}>
                    Download {exportFilename}
                  </button>
                  <button type="button" className="btn" onClick={handleCopyExport}>
                    {exportCopied ? 'Copied!' : 'Copy'}
                  </button>
                  <button type="button" className="btn" onClick={() => setExportingYarn(false)}>
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {importingYarn && sceneId != null && (
          <div className="yarn-import">
            <div className="yarn-import__header">
              Paste a Yarn script — each <code>title:</code> block becomes a chain of nodes;
              <code>-&gt; options</code> and <code>&lt;&lt;jump&gt;&gt;</code> become branches
              (into new nodes or existing ones, by title).
            </div>
            {currentId != null && (
              <label className="yarn-import__attach">
                <input
                  type="checkbox"
                  checked={attachYarnToCurrent}
                  onChange={(event) => setAttachYarnToCurrent(event.target.checked)}
                />
                Attach the first node to the one currently open
                {attachYarnToCurrent && detail && (
                  <span className="yarn-import__attach-preview">
                    “{(detail.text || '(no text)').slice(0, 60)}”
                  </span>
                )}
              </label>
            )}
            <textarea
              className="yarn-import__text"
              value={yarnText}
              onChange={(event) => setYarnText(event.target.value)}
              placeholder={'title: Greeting\n---\nGuide: Welcome, traveler.\n-> Tell me more.\n    <<jump Danger>>\n===\n'}
              rows={10}
            />
            <div className="yarn-import__actions">
              <button type="button" className="btn btn--primary" onClick={handleImportYarn}>
                Import
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setImportingYarn(false);
                  setYarnText('');
                  setYarnError(null);
                  setYarnWarnings([]);
                }}
              >
                Close
              </button>
            </div>
            {yarnError && <p className="dialogue-editor__error">{yarnError}</p>}
            {yarnWarnings.length > 0 && (
              <ul className="yarn-import__warnings">
                {yarnWarnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {error && <p className="dialogue-editor__error">{error}</p>}

        {viewMode === 'tree' ? (
          <>
            {treeNodes.length > 0 ? (
              <DialogueTree nodes={treeNodes} selectedId={currentId} onSelect={setCurrentId} />
            ) : (
              sceneId != null &&
              !error && (
                <p className="dialogue-editor__empty">
                  This scene has no dialogue yet — add the first line.
                </p>
              )
            )}
            {detail && (
              <DialogueBlob
                key={detail.id}
                detail={detail}
                characters={characters}
                stateSchema={(project?.state_schema ?? {}) as StateSchema}
                onSave={handleEdit}
                onCreateCharacter={createCharacter}
              />
            )}
          </>
        ) : detail ? (
          <>
            <div className="dialogue-editor__parent">
              {detail.parents.length === 0 ? (
                <span className="dialogue-editor__root-label">Root dialogue</span>
              ) : detail.parents.length === 1 ? (
                <button
                  type="button"
                  className="dialogue-editor__back"
                  onClick={() => setCurrentId(detail.parents[0].id)}
                >
                  ▲ Back to parent
                </button>
              ) : (
                <div className="dialogue-editor__parent-picker">
                  <span className="dialogue-editor__parent-picker-label">
                    ▲ Back to — reached from {detail.parents.length} places:
                  </span>
                  {detail.parents.map((parent) => (
                    <button
                      key={parent.id}
                      type="button"
                      className="dialogue-editor__back"
                      onClick={() => setCurrentId(parent.id)}
                    >
                      {parent.text || parent.title}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <DialogueBlob
              key={detail.id}
              detail={detail}
              characters={characters}
              stateSchema={(project?.state_schema ?? {}) as StateSchema}
              onSave={handleEdit}
              onCreateCharacter={createCharacter}
            />

            <ResponseWheel responses={detail.responses} onSelect={setCurrentId} />
          </>
        ) : (
          sceneId != null &&
          !error && (
            <p className="dialogue-editor__empty">This scene has no dialogue yet — add the first line.</p>
          )
        )}

        {sceneId != null && (
          <div className="dialogue-editor__add">
            {adding ? (
              <>
                <DialogueForm
                  characters={characters}
                  submitLabel={currentId == null ? 'Add dialogue' : 'Add response'}
                  onSubmit={handleAdd}
                  onCancel={() => {
                    setAdding(false);
                    resetAddRequirementDraft();
                  }}
                  onCreateCharacter={createCharacter}
                />

                {currentId != null && (
                  <div className="dialogue-requirements">
                    <div className="dialogue-effects__header">Only show this response if...</div>
                    <div className="dialogue-effects__row">
                      <select
                        className="dialogue-effects__select"
                        value={addRequirementType}
                        onChange={(event) => {
                          setAddRequirementType(
                            event.target.value as 'remembered_choice' | 'has_item' | 'stat_check' | 'flag',
                          );
                          setAddRequirementStateKey('');
                        }}
                      >
                        <option value="remembered_choice">Player previously chose</option>
                        <option value="has_item">Player has item</option>
                        <option value="stat_check">Stat check</option>
                        <option value="flag">Flag is</option>
                      </select>

                      <MemoryComboBox
                        entries={getStateEntriesForRequirement(
                          (project?.state_schema ?? {}) as StateSchema,
                          addRequirementType,
                        )}
                        value={addRequirementStateKey}
                        placeholder="Search memory..."
                        onChange={setAddRequirementStateKey}
                      />

                      {addRequirementType === 'stat_check' && (
                        <>
                          <select
                            className="dialogue-effects__select"
                            value={addRequirementStatOp}
                            onChange={(event) =>
                              setAddRequirementStatOp(event.target.value as 'at_least' | 'less_than' | 'equals')
                            }
                          >
                            <option value="at_least">is at least</option>
                            <option value="less_than">is less than</option>
                            <option value="equals">equals</option>
                          </select>
                          <input
                            className="dialogue-effects__number"
                            type="number"
                            value={addRequirementValue}
                            onChange={(event) => setAddRequirementValue(Number(event.target.value))}
                          />
                        </>
                      )}

                      {addRequirementType === 'flag' && (
                        <select
                          className="dialogue-effects__select"
                          value={addRequirementFlagValue ? 'true' : 'false'}
                          onChange={(event) => setAddRequirementFlagValue(event.target.value === 'true')}
                        >
                          <option value="true">Yes</option>
                          <option value="false">No</option>
                        </select>
                      )}

                      <button type="button" className="dialogue-effects__add" onClick={handleAddRequirement}>
                        Add requirement
                      </button>
                    </div>

                    {addRequirements.length > 0 && (
                      <div className="dialogue-effects__list">
                        {addRequirements.map((requirement, index) => (
                          <span
                            key={`${requirement.type}-${requirement.state_key}-${index}`}
                            className="dialogue-badge dialogue-badge--requirement"
                          >
                            {getRequirementLabel(requirement, (project?.state_schema ?? {}) as StateSchema)}
                            <button
                              type="button"
                              className="dialogue-badge__remove"
                              onClick={() => handleRemoveAddRequirement(index)}
                              aria-label="Remove requirement"
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="dialogue-editor__add-actions">
                <button
                  type="button"
                  className="btn btn--add"
                  onClick={() => {
                    setLinking(false);
                    setAdding(true);
                  }}
                >
                  {addLabel}
                </button>
                {currentId != null && (
                  <button type="button" className="btn" onClick={openLinkPicker}>
                    🔗 Merge existing node
                  </button>
                )}
              </div>
            )}

            {linking && !adding && currentId != null && (
              <div className="dialogue-link">
                <div className="dialogue-effects__header">
                  Point this node at an existing one (multiple branches → the same response)
                </div>
                <div className="dialogue-effects__row">
                  <select
                    className="dialogue-effects__select"
                    value={linkTargetId ?? ''}
                    onChange={(event) =>
                      setLinkTargetId(event.target.value ? Number(event.target.value) : null)
                    }
                  >
                    <option value="">Choose a node…</option>
                    {linkableCandidates.map((node) => (
                      <option key={node.id} value={node.id}>
                        {(node.character?.name ? `${node.character.name}: ` : '') +
                          (node.text || node.title)}
                      </option>
                    ))}
                  </select>
                  <input
                    className="dialogue-effects__input"
                    value={linkOptionLabel}
                    placeholder="Option label (optional)"
                    onChange={(event) => setLinkOptionLabel(event.target.value)}
                  />
                  <button
                    type="button"
                    className="dialogue-effects__add"
                    onClick={handleLink}
                    disabled={linkTargetId == null}
                  >
                    Merge
                  </button>
                  <button type="button" className="btn" onClick={() => setLinking(false)}>
                    Cancel
                  </button>
                </div>
                {linkableCandidates.length === 0 && (
                  <p className="response-wheel__empty">No other nodes in this scene to merge into yet.</p>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      <CharactersSidebar characters={characters} />
    </div>
  );
}
