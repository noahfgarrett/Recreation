import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, FilePlus2, FolderOpen, Loader2, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Redo2, ShieldCheck, Undo2 } from 'lucide-react';
import { RecreationApi, selectImportFiles, startService, type ImportFileSelection } from './api/client';
import { Canvas, type FocusNodeFn } from './components/Canvas';
import { ContextMenu, type ContextMenuAction } from './components/ContextMenu';
import { DrawingWorkspace } from './components/drawing/DrawingWorkspace';
import { Inspector } from './components/Inspector';
import { PdfPagePicker } from './components/PdfPagePicker';
import { PreflightReviewModal } from './components/PreflightReviewModal';
import { ProjectList } from './components/ProjectList';
import { ReviewPanel } from './components/ReviewPanel';
import { FilterBar, SearchInput } from './components/SearchBar';
import { ShortcutsModal } from './components/ShortcutsModal';
import { SourceViewer, type SourceViewerTarget } from './components/SourceViewer';
import { StatusStrip } from './components/StatusStrip';
import { ThemeToggle } from './components/ThemeToggle';
import { useTheme } from './hooks/useTheme';
import { connectedDemoGraph, connectedDemoProject } from './lib/connectedDemoGraph';
import { useUndoRedo } from './hooks/useUndoRedo';
import { openReviewCount } from './lib/graphAdapters';
import type { ConfidenceLevel } from './lib/graphAdapters';
import type { DrawingDocument, DrawingGraph, HierarchyTemplate, JobStatus, LayoutOption, NodeKind, PreflightReview, Project, ReviewItem, ServiceInfo, SourceEvidence } from './types';

const EMPTY_GRAPH: DrawingGraph = {
  projectId: '',
  nodes: [],
  edges: [],
  reviewItems: [],
};

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const connectedDemo = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('demo') === 'connected-pids';
  }, []);

  const [service, setService] = useState<ServiceInfo | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [graph, setGraph] = useState<DrawingGraph>(EMPTY_GRAPH);
  const [layoutOptions, setLayoutOptions] = useState<LayoutOption[]>([]);
  const [drawing, setDrawing] = useState<DrawingDocument | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState('Starting local service');
  const [busy, setBusy] = useState(false);

  const [projects, setProjects] = useState<Project[]>([]);
  const [showProjectList, setShowProjectList] = useState(false);
  const [pagePickerRequest, setPagePickerRequest] = useState<{
    paths: string[];
    resolve: (files: ImportFileSelection[] | null) => void;
  } | null>(null);
  const [preflightRequest, setPreflightRequest] = useState<{
    review: PreflightReview;
    resolve: (review: PreflightReview | null) => void;
  } | null>(null);
  const [preflightTemplates, setPreflightTemplates] = useState<HierarchyTemplate[]>([]);
  const [sourceViewerTarget, setSourceViewerTarget] = useState<SourceViewerTarget | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuAction | null>(null);
  const projectRequestIdRef = useRef(0);
  const sourceFileCacheRef = useRef<Map<string, { name: string; pageCount: number }>>(new Map());
  const autoLoadedProjectIdRef = useRef<string | null>(null);

  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [filterKind, setFilterKind] = useState<NodeKind | null>(null);
  const [filterConfidence, setFilterConfidence] = useState<ConfidenceLevel | null>(null);
  const [filterSheet, setFilterSheet] = useState<number | null>(null);
  const searchFilter = useMemo(
    () => ({ query: searchQuery, kind: filterKind, confidence: filterConfidence, sheet: filterSheet }),
    [searchQuery, filterKind, filterConfidence, filterSheet],
  );
  const availableSheets = useMemo(() => {
    const sheets = new Set<number>();
    for (const node of graph.nodes) {
      const page = node.sourceEvidence[0]?.page ?? 0;
      if (page > 0) sheets.add(page);
    }
    return [...sheets].sort((a, b) => a - b);
  }, [graph.nodes]);
  const activeLayoutOptionId = useMemo(
    () => (drawing ? layoutOptions.find((option) => option.drawingId === drawing.id)?.id ?? null : null),
    [drawing, layoutOptions],
  );
  const primaryLayoutOptions = useMemo(() => {
    const primary = layoutOptions.filter((option) => option.metrics.primaryOutput === true || option.metrics.sourceDriven === true);
    return primary.length > 0 ? primary : layoutOptions;
  }, [layoutOptions]);

  const focusNodeRef = useRef<FocusNodeFn | null>(null);
  const { pushState, undo, redo, canUndo, canRedo } = useUndoRedo(graph, setGraph);

  const api = useMemo(() => (service ? new RecreationApi(service.baseUrl) : null), [service]);
  const choosePageSelections = useCallback((paths: string[]) => {
    return new Promise<ImportFileSelection[] | null>((resolve) => {
      setPagePickerRequest({ paths, resolve });
    });
  }, []);
  const reviewPreflight = useCallback((review: PreflightReview) => {
    return new Promise<PreflightReview | null>((resolve) => {
      setPreflightRequest({ review, resolve });
    });
  }, []);

  const resetProjectScopedState = useCallback((nextGraph: DrawingGraph = EMPTY_GRAPH) => {
    setGraph(nextGraph);
    setLayoutOptions([]);
    setDrawing(null);
    setSelectedId(null);
    setSourceViewerTarget(null);
    setContextMenu(null);
    setPreflightTemplates([]);
    sourceFileCacheRef.current.clear();
  }, []);

  const beginProjectRequest = useCallback(() => {
    projectRequestIdRef.current += 1;
    setJob(null);
    resetProjectScopedState();
    return projectRequestIdRef.current;
  }, [resetProjectScopedState]);

  useEffect(() => {
    if (connectedDemo) return;
    let cancelled = false;
    setMessage('Starting local extractor...');
    startService()
      .then(async (info) => {
        if (cancelled) return;
        setMessage(info.mode === 'tauri' ? 'Starting packaged extractor...' : 'Connecting to browser dev backend');
        try {
          const client = new RecreationApi(info.baseUrl);
          await waitForServiceReady(client, info.mode === 'tauri' ? 90 : 20, 500);
          if (!cancelled) {
            setService(info);
            setMessage('Ready');
            const list = await client.listProjects();
            if (!cancelled) setProjects(list);
          }
        } catch {
          if (!cancelled) setMessage(`Backend not reachable at ${info.baseUrl}`);
        }
      })
      .catch((error) => setMessage(`Service start failed: ${error instanceof Error ? error.message : String(error)}`));
    return () => {
      cancelled = true;
    };
  }, [connectedDemo]);

  useEffect(() => {
    if (!connectedDemo) return;
    setService({
      baseUrl: 'http://localhost:8765',
      port: 8765,
      dataDir: 'demo',
      mode: 'browser',
    });
    setProject(connectedDemoProject);
    setProjects([connectedDemoProject]);
    projectRequestIdRef.current += 1;
    resetProjectScopedState(connectedDemoGraph);
    setSelectedId('sc-02');
    setLeftCollapsed(true);
    setRightCollapsed(true);
    setMessage('Demo loaded: 5 P&ID sheets connected, 0 open reviews');
  }, [connectedDemo, resetProjectScopedState]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if (drawing) return;
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        undo();
      }
      if ((e.metaKey || e.ctrlKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        redo();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [drawing, undo, redo]);

  const importPackage = useCallback(async () => {
    if (!api) return;
    let paths: string[];
    try {
      paths = await chooseFiles();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'File selection failed');
      return;
    }
    if (paths.length === 0) {
      setMessage('No files selected');
      return;
    }
    const selectedFiles = await choosePageSelections(paths);
    if (!selectedFiles || selectedFiles.length === 0) {
      setMessage('No pages selected');
      return;
    }

    const requestId = beginProjectRequest();
    const isCurrentRequest = () => projectRequestIdRef.current === requestId;
    const setCurrentJob = (nextJob: JobStatus) => {
      if (isCurrentRequest()) setJob(nextJob);
    };
    const clearFailedImportProject = () => {
      setProject(null);
      resetProjectScopedState();
      setPreflightRequest(null);
    };

    setBusy(true);
    try {
      const created = await api.createProject(`Recreation ${new Date().toLocaleString()}`);
      if (!isCurrentRequest()) return;
      setProject(created);
      setMessage(`Importing ${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'}`);
      await api.importFiles(created.id, selectedFiles);
      if (!isCurrentRequest()) return;
      setMessage('Scanning drawing package for discipline, legends, and page roles');
      const draftPreflight = await api.runPreflight(created.id);
      if (!isCurrentRequest()) return;
      let hierarchyTemplates: HierarchyTemplate[] = [];
      try {
        hierarchyTemplates = await api.listHierarchyTemplates();
      } catch (error) {
        console.warn('Unable to load hierarchy templates for preflight review', error);
      }
      if (!isCurrentRequest()) return;
      setPreflightTemplates(hierarchyTemplates);
      const confirmedPreflight = await reviewPreflight(draftPreflight);
      if (!isCurrentRequest()) return;
      if (!confirmedPreflight) {
        setMessage('Preflight cancelled');
        clearFailedImportProject();
        return;
      }
      await api.confirmPreflight(created.id, confirmedPreflight);
      if (!isCurrentRequest()) return;
      setMessage('Preflight confirmed; extracting drawing evidence');
      const { jobId } = await api.startExtract(created.id);
      if (!isCurrentRequest()) return;
      await trackJob(api, jobId, setCurrentJob, 'Extraction failed');
      if (!isCurrentRequest()) return;
      const nextGraph = await api.getGraph(created.id);
      if (!isCurrentRequest()) return;
      setGraph(nextGraph);
      setMessage('Generating combined P&ID layout options');
      const stitch = await api.startStitch(created.id);
      if (!isCurrentRequest()) return;
      await trackJob(api, stitch.jobId, setCurrentJob, 'Stitching failed');
      if (!isCurrentRequest()) return;
      const options = await api.listLayoutOptions(created.id);
      if (!isCurrentRequest()) return;
      const selectedOption = selectLayoutOption(options);
      const nextDrawing = selectedOption ? await loadDrawingForOption(api, created.id, selectedOption) : null;
      if (!isCurrentRequest()) return;
      setLayoutOptions(options);
      setDrawing(nextDrawing);
      setMessage(
        `Combined P&ID ready: ${formatLayoutOptionCount(options.length)} generated from ${nextGraph.nodes.length} nodes, ${openReviewCount(nextGraph)} reviews`,
      );
      try {
        const list = await api.listProjects();
        if (!isCurrentRequest()) return;
        setProjects(list);
      } catch {
        // The imported project is already active; a refresh failure should not discard it.
      }
    } catch (error) {
      if (isCurrentRequest()) {
        clearFailedImportProject();
        setMessage(error instanceof Error ? error.message : 'Import failed');
      }
    } finally {
      if (isCurrentRequest()) setBusy(false);
    }
  }, [api, beginProjectRequest, choosePageSelections, resetProjectScopedState, reviewPreflight]);

  const loadProject = useCallback(
    async (proj: Project, options?: { preferredLayout?: string }) => {
      if (!api) return;
      const requestId = beginProjectRequest();
      const isCurrentRequest = () => projectRequestIdRef.current === requestId;
      setBusy(true);
      try {
        setProject(proj);
        const nextGraph = await api.getGraph(proj.id);
        if (!isCurrentRequest()) return;
        setGraph(nextGraph);
        const layoutOptionsFromApi = await api.listLayoutOptions(proj.id);
        if (!isCurrentRequest()) return;
        const selectedOption = selectLayoutOption(layoutOptionsFromApi, options?.preferredLayout);
        const nextDrawing = selectedOption ? await loadDrawingForOption(api, proj.id, selectedOption) : null;
        if (!isCurrentRequest()) return;
        setLayoutOptions(layoutOptionsFromApi);
        setDrawing(nextDrawing);
        setMessage(
          layoutOptionsFromApi.length > 0
            ? `Loaded: ${proj.name} (${formatLayoutOptionCount(layoutOptionsFromApi.length)})`
            : `Loaded: ${proj.name}`,
        );
      } catch (error) {
        if (isCurrentRequest()) {
          resetProjectScopedState();
          setMessage(error instanceof Error ? error.message : 'Failed to load project');
        }
      } finally {
        if (isCurrentRequest()) setBusy(false);
      }
    },
    [api, beginProjectRequest, resetProjectScopedState],
  );

  useEffect(() => {
    if (connectedDemo || !api || projects.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const projectId = params.get('projectId');
    if (!projectId || autoLoadedProjectIdRef.current === projectId) return;
    const linkedProject = projects.find((candidate) => candidate.id === projectId);
    if (!linkedProject) {
      setMessage(`Project link not found: ${projectId}`);
      return;
    }
    autoLoadedProjectIdRef.current = projectId;
    void loadProject(linkedProject, { preferredLayout: params.get('layout') ?? undefined });
  }, [api, connectedDemo, loadProject, projects]);

  const handleGraphChange = useCallback(
    (nextGraph: DrawingGraph) => {
      pushState(nextGraph);
    },
    [pushState],
  );

  const saveLayout = useCallback(
    async (nextGraph: DrawingGraph) => {
      if (!api || !project) {
        setGraph(nextGraph);
        setMessage('Layout updated locally');
        return;
      }
      setGraph(await api.updateLayout(project.id, nextGraph));
      setMessage('Layout saved');
    },
    [api, project],
  );

  const navigateToNode = useCallback((nodeId: string) => {
    focusNodeRef.current?.(nodeId);
  }, []);

  const toggleLock = useCallback((nodeId: string) => {
    setGraph((current) => ({
      ...current,
      nodes: current.nodes.map((node) => (node.id === nodeId ? { ...node, locked: !node.locked } : node)),
    }));
  }, []);

  const bulkLock = useCallback((nodeIds: string[], lock: boolean) => {
    const ids = new Set(nodeIds);
    setGraph((current) => ({
      ...current,
      nodes: current.nodes.map((node) => (ids.has(node.id) ? { ...node, locked: lock } : node)),
    }));
  }, []);

  const bulkDelete = useCallback(
    async (nodeIds: string[]) => {
      const ids = new Set(nodeIds);
      if (api && project) {
        try {
          for (const nodeId of nodeIds) {
            await api.deleteNode(project.id, nodeId);
          }
          setGraph(await api.getGraph(project.id));
          setMessage(`Deleted ${nodeIds.length} nodes`);
          return;
        } catch (error) {
          setMessage(error instanceof Error ? error.message : 'Bulk delete failed');
        }
      }
      setGraph((current) => ({
        ...current,
        nodes: current.nodes.filter((node) => !ids.has(node.id)),
        edges: current.edges.filter(
          (edge) => !ids.has(edge.sourcePort.split(':')[0]) && !ids.has(edge.targetPort.split(':')[0]),
        ),
      }));
    },
    [api, project],
  );

  const updateNode = useCallback(
    async (nodeId: string, updates: { tag?: string; kind?: NodeKind }) => {
      if (api && project) {
        try {
          await api.updateNode(project.id, nodeId, updates);
          setGraph(await api.getGraph(project.id));
          setMessage('Tag updated');
          return;
        } catch (error) {
          setMessage(error instanceof Error ? error.message : 'Update failed');
        }
      }
      setGraph((current) => ({
        ...current,
        nodes: current.nodes.map((node) => (node.id === nodeId ? { ...node, ...updates } : node)),
      }));
    },
    [api, project],
  );

  const updateEdge = useCallback(
    async (edgeId: string, updates: { label?: string; lineOrCableId?: string }) => {
      if (api && project) {
        try {
          await api.updateEdge(project.id, edgeId, updates);
          setGraph(await api.getGraph(project.id));
          setMessage('Connection updated');
          return;
        } catch (error) {
          setMessage(error instanceof Error ? error.message : 'Edge update failed');
        }
      }
      setGraph((current) => ({
        ...current,
        edges: current.edges.map((edge) => (edge.id === edgeId ? { ...edge, ...updates } : edge)),
      }));
    },
    [api, project],
  );

  const deleteNode = useCallback(
    async (nodeId: string) => {
      if (api && project) {
        try {
          await api.deleteNode(project.id, nodeId);
          setGraph(await api.getGraph(project.id));
          setMessage('Node deleted');
          return;
        } catch (error) {
          setMessage(error instanceof Error ? error.message : 'Delete failed');
        }
      }
      setGraph((current) => ({
        ...current,
        nodes: current.nodes.filter((node) => node.id !== nodeId),
        edges: current.edges.filter(
          (edge) => !edge.sourcePort.startsWith(nodeId) && !edge.targetPort.startsWith(nodeId),
        ),
      }));
    },
    [api, project],
  );

  const openSourceViewer = useCallback(
    async (evidence: SourceEvidence, allEvidence: SourceEvidence[]) => {
      const requestId = projectRequestIdRef.current;
      const fileId = evidence.sourceFileId;

      // Try cache first
      let fileInfo = sourceFileCacheRef.current.get(fileId);

      // Fetch source file info if not cached
      if (!fileInfo && api && project) {
        try {
          const sources = await api.listSources(project.id);
          if (projectRequestIdRef.current !== requestId) return;
          for (const src of sources) {
            sourceFileCacheRef.current.set(src.id, { name: src.name, pageCount: src.pageCount });
          }
          fileInfo = sourceFileCacheRef.current.get(fileId);
        } catch {
          // Fall through to defaults
        }
      }
      if (projectRequestIdRef.current !== requestId) return;

      setSourceViewerTarget({
        sourceFileId: fileId,
        sourceFileName: fileInfo?.name ?? fileId,
        page: evidence.page,
        totalPages: fileInfo?.pageCount ?? evidence.page,
        bounds: evidence.bounds,
        allEvidence,
      });
    },
    [api, project],
  );

  const resolveReview = useCallback(
    async (item: ReviewItem, resolution: Record<string, unknown>): Promise<void> => {
      if (!api || !project) {
        setGraph((current) => ({
          ...current,
          reviewItems: current.reviewItems.map((entry) =>
            entry.id === item.id ? { ...entry, status: 'resolved' as const, resolution, resolvedBy: 'user' } : entry,
          ),
        }));
        return;
      }
      try {
        // Optimistic update: mark resolved locally first so the UI responds instantly
        setGraph((current) => ({
          ...current,
          reviewItems: current.reviewItems.map((entry) =>
            entry.id === item.id ? { ...entry, status: 'resolved' as const, resolution, resolvedBy: 'user' } : entry,
          ),
        }));
        await api.resolveReview(project.id, item.id, resolution);
        setMessage('Review decision saved');
      } catch (error) {
        // Revert on failure: re-fetch graph from server to get the true state
        setMessage(error instanceof Error ? error.message : 'Failed to save review decision');
        try {
          setGraph(await api.getGraph(project.id));
        } catch {
          // If refetch also fails, the optimistic update stays — at least the UI is usable
        }
      }
    },
    [api, project],
  );

  const handleDrawingChange = useCallback((next: DrawingDocument) => {
    setDrawing(next);
  }, []);

  const chooseLayout = useCallback(
    async (option: LayoutOption) => {
      if (!api || !project) return;
      const requestId = projectRequestIdRef.current;
      setBusy(true);
      try {
        const nextDrawing = await api.getDrawing(project.id, option.drawingId);
        if (projectRequestIdRef.current !== requestId) return;
        setDrawing(nextDrawing);
        setMessage(`Loaded layout: ${option.name}`);
      } catch (error) {
        if (projectRequestIdRef.current === requestId) {
          setMessage(error instanceof Error ? error.message : 'Failed to load layout');
        }
      } finally {
        if (projectRequestIdRef.current === requestId) setBusy(false);
      }
    },
    [api, project],
  );

  const saveDrawing = useCallback(
    async (nextDrawing?: DrawingDocument) => {
      const currentDrawing = nextDrawing ?? drawing;
      if (!currentDrawing) return;
      if (!api || !project) {
        setDrawing(currentDrawing);
        setMessage('Drawing updated locally');
        return;
      }
      const requestId = projectRequestIdRef.current;
      setBusy(true);
      try {
        const savedDrawing = await api.updateDrawing(project.id, currentDrawing);
        if (projectRequestIdRef.current !== requestId) return;
        setDrawing(savedDrawing);
        setLayoutOptions((currentOptions) =>
          currentOptions.map((option) =>
            option.drawingId === savedDrawing.id ? { ...option, drawingDocument: savedDrawing } : option,
          ),
        );
        setMessage('Drawing saved');
      } catch (error) {
        if (projectRequestIdRef.current === requestId) {
          setMessage(error instanceof Error ? error.message : 'Drawing save failed');
        }
      } finally {
        if (projectRequestIdRef.current === requestId) setBusy(false);
      }
    },
    [api, drawing, project],
  );

  const exportDrawingSvg = useCallback(
    async (nextDrawing?: DrawingDocument) => {
      const currentDrawing = nextDrawing ?? drawing;
      if (!api || !project || !currentDrawing) {
        setMessage('Open a drawing before exporting');
        return;
      }
      const requestId = projectRequestIdRef.current;
      setBusy(true);
      try {
        const savedDrawing = await api.updateDrawing(project.id, currentDrawing);
        if (projectRequestIdRef.current !== requestId) return;
        setDrawing(savedDrawing);
        setLayoutOptions((currentOptions) =>
          currentOptions.map((option) =>
            option.drawingId === savedDrawing.id ? { ...option, drawingDocument: savedDrawing } : option,
          ),
        );
        const result = await api.exportDrawing(project.id, savedDrawing.id, 'svg');
        if (projectRequestIdRef.current !== requestId) return;
        setMessage(`Exported drawing SVG to ${result.path}`);
      } catch (error) {
        if (projectRequestIdRef.current === requestId) {
          setMessage(error instanceof Error ? error.message : 'Drawing SVG export failed');
        }
      } finally {
        if (projectRequestIdRef.current === requestId) setBusy(false);
      }
    },
    [api, drawing, project],
  );

  const exportDrawingPdf = useCallback(
    async (nextDrawing?: DrawingDocument) => {
      const currentDrawing = nextDrawing ?? drawing;
      if (!api || !project || !currentDrawing) {
        setMessage('Open a drawing before exporting');
        return;
      }
      const requestId = projectRequestIdRef.current;
      setBusy(true);
      try {
        const savedDrawing = await api.updateDrawing(project.id, currentDrawing);
        if (projectRequestIdRef.current !== requestId) return;
        setDrawing(savedDrawing);
        setLayoutOptions((currentOptions) =>
          currentOptions.map((option) =>
            option.drawingId === savedDrawing.id ? { ...option, drawingDocument: savedDrawing } : option,
          ),
        );
        const result = await api.exportDrawing(project.id, savedDrawing.id, 'pdf');
        if (projectRequestIdRef.current !== requestId) return;
        setMessage(`Exported drawing PDF to ${result.path}`);
      } catch (error) {
        if (projectRequestIdRef.current === requestId) {
          setMessage(error instanceof Error ? error.message : 'Drawing PDF export failed');
        }
      } finally {
        if (projectRequestIdRef.current === requestId) setBusy(false);
      }
    },
    [api, drawing, project],
  );

  const exportType = useCallback(
    async (type: 'svg' | 'pdf' | 'xlsx') => {
      if (!api || !project) {
        setMessage('Create or import a project before exporting');
        return;
      }
      setBusy(true);
      try {
        const result = await api.export(project.id, type);
        setMessage(`Exported ${type.toUpperCase()} to ${result.path}`);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Export failed');
      } finally {
        setBusy(false);
      }
    },
    [api, project],
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <img className="brand-mark" src="/recreation-logo.svg" alt="" aria-hidden="true" />
          <div>
            <h1>Recreation</h1>
            <p>{project?.name ?? 'P&ID Drawing Reconstruction'}</p>
          </div>
        </div>
        <div className="topbar-meta" aria-label="Project status">
          {drawing ? (
            <>
              <span>{drawing.objects.length} objects</span>
              <span>{primaryLayoutOptions.length} output{primaryLayoutOptions.length === 1 ? '' : 's'}</span>
              <span>{drawing.sourcePages.length} pages</span>
            </>
          ) : (
            <>
              <span>{graph.nodes.length} tags</span>
              <span>{graph.edges.length} connections</span>
              <span>{openReviewCount(graph)} reviews</span>
            </>
          )}
        </div>
        <nav className="topbar-actions" aria-label="Primary actions">
          <button onClick={() => setShowProjectList(true)} disabled={!api} title="Open project">
            <FolderOpen size={16} />
          </button>
          <button onClick={importPackage} disabled={!api || busy}>
            {busy ? <Loader2 className="spin" size={16} /> : <FilePlus2 size={16} />}
            Import
          </button>
          <button onClick={undo} disabled={Boolean(drawing) || !canUndo} title="Undo (Ctrl+Z)">
            <Undo2 size={16} />
          </button>
          <button onClick={redo} disabled={Boolean(drawing) || !canRedo} title="Redo (Ctrl+Y)">
            <Redo2 size={16} />
          </button>
          <button className="btn-primary" onClick={() => (drawing ? saveDrawing(drawing) : saveLayout(graph))}>
            <ShieldCheck size={16} />
            Save
          </button>
          <div className="export-group">
            <button title="Export SVG" onClick={() => (drawing ? exportDrawingSvg(drawing) : exportType('svg'))}>
              <Download size={15} />
              SVG
            </button>
            <button title="Export PDF" onClick={() => (drawing ? exportDrawingPdf(drawing) : exportType('pdf'))}>
              PDF
            </button>
            <button title="Export XLSX" onClick={() => exportType('xlsx')}>
              XLSX
            </button>
          </div>
          <ShortcutsModal />
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </nav>
      </header>

      {drawing ? null : (
        <div className={`search-strip${leftCollapsed ? ' search-strip--left-collapsed' : ''}${rightCollapsed ? ' search-strip--right-collapsed' : ''}`}>
          <div className="search-strip-left">
            <button
              className="panel-toggle"
              onClick={() => setLeftCollapsed((prev) => !prev)}
              title={leftCollapsed ? 'Show review panel' : 'Hide review panel'}
            >
              {leftCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
            </button>
            <SearchInput onSearch={setSearchQuery} />
          </div>
          <div className="search-strip-center">
            <FilterBar
              onFilterKind={setFilterKind}
              activeKind={filterKind}
              onFilterConfidence={setFilterConfidence}
              activeConfidence={filterConfidence}
              availableSheets={availableSheets}
              activeSheet={filterSheet}
              onFilterSheet={setFilterSheet}
            />
          </div>
          <div className="search-strip-right">
            <button
              className="panel-toggle"
              onClick={() => setRightCollapsed((prev) => !prev)}
              title={rightCollapsed ? 'Show inspector' : 'Hide inspector'}
            >
              {rightCollapsed ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />}
            </button>
          </div>
        </div>
      )}

      {drawing ? (
        <div style={{ gridRow: '2 / 4', minHeight: 0 }}>
          <DrawingWorkspace
            drawing={drawing}
            layoutOptions={primaryLayoutOptions}
            activeLayoutOptionId={activeLayoutOptionId}
            onChooseLayoutOption={chooseLayout}
            onChange={handleDrawingChange}
            onSave={saveDrawing}
            onExportSvg={exportDrawingSvg}
            onExportPdf={exportDrawingPdf}
            apiBaseUrl={service?.baseUrl}
          />
        </div>
      ) : (
        <section className={`workspace${leftCollapsed ? ' workspace--left-collapsed' : ''}${rightCollapsed ? ' workspace--right-collapsed' : ''}`}>
          <div className={`panel-slot panel-slot--left${leftCollapsed ? ' panel-slot--collapsed' : ''}`}>
            {leftCollapsed ? null : (
              <ReviewPanel items={graph.reviewItems} onResolve={resolveReview} onNavigateToNode={navigateToNode} />
            )}
          </div>
          <Canvas
            graph={graph}
            onGraphChange={handleGraphChange}
            onSaveLayout={saveLayout}
            onSelectElement={setSelectedId}
            onNodeContextMenu={(nodeId, x, y) => setContextMenu({ nodeId, x, y })}
            onBulkLock={bulkLock}
            onBulkDelete={bulkDelete}
            onReady={(fn) => { focusNodeRef.current = fn; }}
            searchFilter={searchFilter}
            theme={theme}
          />
          <div className={`panel-slot panel-slot--right${rightCollapsed ? ' panel-slot--collapsed' : ''}`}>
            {rightCollapsed ? null : (
              <Inspector
                graph={graph}
                selectedId={selectedId}
                onToggleLock={toggleLock}
                onOpenEvidence={openSourceViewer}
                onUpdateNode={updateNode}
                onUpdateEdge={updateEdge}
              />
            )}
          </div>
        </section>
      )}

      <StatusStrip service={service} job={job} message={message} />

      {graph.nodes.length === 0 && !busy && !drawing ? (
        <div className="empty-state-overlay">
          <div className="empty-state">
            <div className="empty-state-icon">
              <FilePlus2 size={40} />
            </div>
            <h2>No Drawing Loaded</h2>
            <p>Import P&ID PDF files to begin reconstruction, or open an existing project.</p>
            <div className="empty-state-actions">
              <button className="btn-primary" onClick={importPackage} disabled={!api}>
                <FilePlus2 size={16} />
                Import PDFs
              </button>
              <button onClick={() => setShowProjectList(true)} disabled={!api}>
                <FolderOpen size={16} />
                Open Project
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <ContextMenu
        action={contextMenu}
        isLocked={graph.nodes.find((n) => n.id === contextMenu?.nodeId)?.locked ?? false}
        onEditTag={(nodeId) => {
          setSelectedId(nodeId);
        }}
        onToggleLock={toggleLock}
        onDeleteNode={deleteNode}
        onClose={() => setContextMenu(null)}
      />

      {showProjectList ? (
        <ProjectList
          projects={projects}
          currentProjectId={project?.id ?? null}
          onSelect={loadProject}
          onNew={() => {
            setShowProjectList(false);
            importPackage();
          }}
          onClose={() => setShowProjectList(false)}
        />
      ) : null}

      {pagePickerRequest && api ? (
        <PdfPagePicker
          api={api}
          paths={pagePickerRequest.paths}
          onCancel={() => {
            pagePickerRequest.resolve(null);
            setPagePickerRequest(null);
          }}
          onConfirm={(files) => {
            pagePickerRequest.resolve(files);
            setPagePickerRequest(null);
          }}
        />
      ) : null}

      {preflightRequest ? (
        <PreflightReviewModal
          review={preflightRequest.review}
          templates={preflightTemplates}
          onCancel={() => {
            preflightRequest.resolve(null);
            setPreflightRequest(null);
          }}
          onConfirm={(review) => {
            preflightRequest.resolve(review);
            setPreflightRequest(null);
          }}
        />
      ) : null}

      {sourceViewerTarget && service ? (
        <SourceViewer
          target={sourceViewerTarget}
          apiBaseUrl={service.baseUrl}
          projectId={graph.projectId}
          onClose={() => setSourceViewerTarget(null)}
        />
      ) : null}
    </main>
  );
}

async function chooseFiles(): Promise<string[]> {
  const selected = await selectImportFiles();
  if (selected.length > 0) {
    return selected;
  }
  const typed = window.prompt('Browser dev mode: enter comma-separated PDF paths.');
  return typed
    ? typed
        .split(',')
        .map((path) => path.trim())
        .filter(Boolean)
    : [];
}

async function waitForServiceReady(api: RecreationApi, attempts = 20, delayMs = 250): Promise<void> {
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      await api.health();
      return;
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Backend not reachable');
}

async function loadDrawingForOption(
  api: RecreationApi,
  projectId: string,
  option: LayoutOption,
): Promise<DrawingDocument> {
  return option.drawingDocument ?? api.getDrawing(projectId, option.drawingId);
}

function formatLayoutOptionCount(count: number): string {
  return `${count} layout option${count === 1 ? '' : 's'}`;
}

function selectLayoutOption(options: LayoutOption[], preferredLayout?: string): LayoutOption | null {
  if (options.length === 0) return null;
  if (!preferredLayout) {
    return options.find((option) => option.metrics.primaryOutput === true || option.metrics.sourceDriven === true) ?? options[0];
  }
  const normalized = preferredLayout.trim().toLowerCase();
  return (
    options.find((option) => option.id.toLowerCase() === normalized || option.name.toLowerCase() === normalized) ??
    options[0]
  );
}

async function trackJob(
  api: RecreationApi,
  jobId: string,
  setJob: (job: JobStatus) => void,
  failureMessage = 'Job failed',
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    let timeout: number | null = null;
    let unsubscribe: (() => void) | null = null;
    let settled = false;

    const clearWatchdog = () => {
      if (timeout === null) return;
      window.clearTimeout(timeout);
      timeout = null;
    };

    const stopEvents = () => {
      if (!unsubscribe) return;
      const stop = unsubscribe;
      unsubscribe = null;
      stop();
    };

    const cleanup = () => {
      clearWatchdog();
      stopEvents();
    };

    const resolveOnce = () => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve();
    };

    const rejectOnce = (error: unknown) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(toError(error, failureMessage));
    };

    const pollToTerminal = () => {
      clearWatchdog();
      stopEvents();
      pollJob(api, jobId, setJob, failureMessage).then(resolveOnce).catch(rejectOnce);
    };

    try {
      unsubscribe = api.subscribeJobEvents(
        jobId,
        (status) => {
          if (!settled) setJob(status);
        },
        () => {
          clearWatchdog();
          api
            .getJob(jobId)
            .then((final) => {
              if (settled) return;
              setJob(final);
              if (final.status === 'completed') {
                resolveOnce();
              } else if (final.status === 'failed') {
                rejectOnce(new Error(final.error ?? failureMessage));
              } else {
                pollToTerminal();
              }
            })
            .catch(rejectOnce);
        },
      );

      timeout = window.setTimeout(() => {
        pollToTerminal();
      }, 3000);
    } catch {
      pollToTerminal();
    }
  });
}

function toError(error: unknown, fallbackMessage: string): Error {
  return error instanceof Error ? error : new Error(error ? String(error) : fallbackMessage);
}

async function pollJob(
  api: RecreationApi,
  jobId: string,
  setJob: (job: JobStatus) => void,
  failureMessage = 'Job failed',
): Promise<void> {
  for (;;) {
    const next = await api.getJob(jobId);
    setJob(next);
    if (next.status === 'completed') return;
    if (next.status === 'failed') throw new Error(next.error ?? failureMessage);
    await new Promise((r) => window.setTimeout(r, 800));
  }
}
