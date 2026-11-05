import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import type { DrawingBounds, DrawingDocument, DrawingObject, DrawingPoint, DrawingStyle, LayoutOption, PageEvidence } from '../../types';
import { SourceViewer, type SourceViewerTarget } from '../SourceViewer';
import { DrawingCanvas, type DrawingCanvasMode } from './DrawingCanvas';
import { DrawingInspector } from './DrawingInspector';
import { DrawingToolbar } from './DrawingToolbar';
import { LayoutOptionsPanel } from './LayoutOptionsPanel';
import { PidRelationshipTree, type RelationshipTreeRow } from './PidRelationshipTree';
import { routeOrthogonal } from './drawingGeometry';
import { drawingReducer, type DrawingAction } from './drawingReducer';

interface DrawingWorkspaceProps {
  drawing: DrawingDocument;
  layoutOptions?: LayoutOption[];
  activeLayoutOptionId?: string | null;
  selectedId?: string | null;
  onSelectObject?: (id: string | null) => void;
  onChooseLayoutOption?: (option: LayoutOption) => void;
  onChange?: (drawing: DrawingDocument) => void;
  onSave?: (drawing: DrawingDocument) => void | Promise<void>;
  onExportSvg?: (drawing: DrawingDocument) => void | Promise<void>;
  onExportPdf?: (drawing: DrawingDocument) => void | Promise<void>;
  apiBaseUrl?: string | null;
  className?: string;
}

export function DrawingWorkspace({
  drawing,
  layoutOptions = [],
  activeLayoutOptionId,
  selectedId,
  onSelectObject,
  onChooseLayoutOption,
  onChange,
  onSave,
  onExportSvg,
  onExportPdf,
  apiBaseUrl,
  className,
}: DrawingWorkspaceProps) {
  const [localDrawing, setLocalDrawing] = useState(drawing);
  const localDrawingRef = useRef(drawing);
  const externalDrawingIdRef = useRef(drawing.id);
  const [toolMode, setToolMode] = useState<DrawingCanvasMode>('select');
  const [lineStart, setLineStart] = useState<LineDraftStart | null>(null);
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);
  const [internalActiveLayoutId, setInternalActiveLayoutId] = useState<string | null>(activeLayoutOptionId ?? null);
  const [hiddenLayerIds, setHiddenLayerIds] = useState<string[]>([]);
  const [showPrintBoundary, setShowPrintBoundary] = useState(false);
  const [showMinimap, setShowMinimap] = useState(false);
  const [showLineTagRegister, setShowLineTagRegister] = useState(false);
  const [workspaceView, setWorkspaceView] = useState<'drawing' | 'tree'>('drawing');
  const [selectedTreeRow, setSelectedTreeRow] = useState<RelationshipTreeRow | null>(null);
  const [sourceViewerTarget, setSourceViewerTarget] = useState<SourceViewerTarget | null>(null);
  const [fitRequestId, setFitRequestId] = useState(0);
  const [history, setHistory] = useState<{ past: DrawingDocument[]; future: DrawingDocument[] }>({ past: [], future: [] });

  useEffect(() => {
    if (drawing === localDrawingRef.current) {
      return;
    }
    const drawingChanged = drawing.id !== externalDrawingIdRef.current;
    externalDrawingIdRef.current = drawing.id;
    localDrawingRef.current = drawing;
    setLocalDrawing(drawing);
    if (drawingChanged) {
      setHistory({ past: [], future: [] });
      setSourceViewerTarget(null);
      setSelectedTreeRow(null);
    }
  }, [drawing]);

  useEffect(() => {
    if (activeLayoutOptionId !== undefined) {
      setInternalActiveLayoutId(activeLayoutOptionId);
    }
  }, [activeLayoutOptionId]);

  const currentSelectedId = selectedId !== undefined ? selectedId : internalSelectedId;
  const selectedObject = useMemo(
    () => localDrawing.objects.find((object) => object.id === currentSelectedId) ?? null,
    [currentSelectedId, localDrawing.objects],
  );

  const setSelectedObject = useCallback(
    (id: string | null) => {
      if (selectedId === undefined) {
        setInternalSelectedId(id);
      }
      onSelectObject?.(id);
    },
    [onSelectObject, selectedId],
  );

  const commitDrawing = useCallback(
    (nextDrawing: DrawingDocument, options: { recordHistory?: boolean } = {}) => {
      const previous = localDrawingRef.current;
      localDrawingRef.current = nextDrawing;
      setLocalDrawing(nextDrawing);
      if (options.recordHistory) {
        setHistory((current) => ({ past: [...current.past.slice(-24), previous], future: [] }));
      }
      onChange?.(nextDrawing);
    },
    [onChange],
  );

  const applyAction = useCallback(
    (action: DrawingAction) => {
      const current = localDrawingRef.current;
      const next = drawingReducer(current, action);
      if (next !== current) {
        commitDrawing(next, { recordHistory: true });
      }
    },
    [commitDrawing],
  );

  const undo = useCallback(() => {
    setHistory((current) => {
      const previous = current.past.at(-1);
      if (!previous) {
        return current;
      }
      const active = localDrawingRef.current;
      const nextPast = current.past.slice(0, -1);
      localDrawingRef.current = previous;
      setLocalDrawing(previous);
      onChange?.(previous);
      return { past: nextPast, future: [active, ...current.future] };
    });
  }, [onChange]);

  const redo = useCallback(() => {
    setHistory((current) => {
      const next = current.future[0];
      if (!next) {
        return current;
      }
      const active = localDrawingRef.current;
      localDrawingRef.current = next;
      setLocalDrawing(next);
      onChange?.(next);
      return { past: [...current.past, active], future: current.future.slice(1) };
    });
  }, [onChange]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const shortcut = event.metaKey || event.ctrlKey;
      if (!shortcut) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
      } else if (key === 'y' || (key === 'z' && event.shiftKey)) {
        event.preventDefault();
        redo();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [redo, undo]);

  const handleAddRegion = useCallback(() => {
    const region = createDefaultRegion(localDrawingRef.current);
    applyAction({ type: 'addRegion', object: region });
    setSelectedObject(region.id);
    setToolMode('select');
  }, [applyAction, setSelectedObject]);

  const handleAddSymbol = useCallback(
    (symbolType: string) => {
      const symbol = createDefaultSymbol(localDrawingRef.current, symbolType);
      applyAction({ type: 'addObject', object: symbol });
      setSelectedObject(symbol.id);
      setToolMode('select');
      setLineStart(null);
    },
    [applyAction, setSelectedObject],
  );

  const handleModeChange = useCallback((mode: DrawingCanvasMode) => {
    setToolMode(mode);
    if (mode !== 'line') {
      setLineStart(null);
    }
  }, []);

  const handleCreateTextAt = useCallback(
    (point: DrawingPoint) => {
      const textBox = createDefaultTextBox(localDrawingRef.current, point);
      applyAction({ type: 'addObject', object: textBox });
      setSelectedObject(textBox.id);
      setToolMode('select');
      setLineStart(null);
    },
    [applyAction, setSelectedObject],
  );

  const handleLinePoint = useCallback(
    (point: DrawingPoint, objectId: string | null) => {
      if (!lineStart) {
        setLineStart({ point, objectId });
        setToolMode('line');
        return;
      }

      if (lineStart.objectId && lineStart.objectId === objectId) {
        setLineStart({ point, objectId });
        return;
      }

      const connector = createDefaultConnector(localDrawingRef.current, lineStart, { point, objectId });
      applyAction({ type: 'addObject', object: connector });
      setSelectedObject(connector.id);
      setLineStart(null);
      setToolMode('select');
    },
    [applyAction, lineStart, setSelectedObject],
  );

  const handleDeleteObject = useCallback(
    (id: string) => {
      applyAction({ type: 'deleteObject', id });
      setSelectedObject(null);
    },
    [applyAction, setSelectedObject],
  );

  const handleChooseLayoutOption = useCallback(
    (option: LayoutOption) => {
      setInternalActiveLayoutId(option.id);
      onChooseLayoutOption?.(option);
      if (option.drawingDocument) {
        commitDrawing(option.drawingDocument);
        setHistory({ past: [], future: [] });
        setSelectedObject(null);
      }
    },
    [commitDrawing, onChooseLayoutOption, setSelectedObject],
  );

  const toggleLayer = useCallback((layerId: string) => {
    setHiddenLayerIds((current) => (current.includes(layerId) ? current.filter((id) => id !== layerId) : [...current, layerId]));
  }, []);

  const selectedLabel = lineStart
    ? 'Connector: choose endpoint'
    : selectedObject?.label || selectedObject?.id || null;
  const sourceRegister = useMemo(() => readSourceRegister(localDrawing.visualQa), [localDrawing.visualQa]);
  const electricalDocumentGuide = useMemo(() => readElectricalDocumentGuide(localDrawing.visualQa), [localDrawing.visualQa]);
  const sourceRegisterCount = sourceRegister.lineTags.length + sourceRegister.equipment.length;
  const handleOpenSourcePage = useCallback(
    (page: PageEvidence) => {
      setSourceViewerTarget(sourceViewerTargetForPage(page, localDrawing.sourcePages));
    },
    [localDrawing.sourcePages],
  );
  const handleOpenTreeSource = useCallback(
    (row: RelationshipTreeRow) => {
      const target = sourceViewerTargetForTreeRow(row, localDrawing.sourcePages);
      if (target) {
        setSourceViewerTarget(target);
      }
    },
    [localDrawing.sourcePages],
  );

  return (
    <div className={`drawing-workspace${className ? ` ${className}` : ''}`}>
      <LayoutOptionsPanel
        options={layoutOptions}
        activeOptionId={internalActiveLayoutId}
        onChooseOption={handleChooseLayoutOption}
        drawing={localDrawing}
        hiddenLayerIds={hiddenLayerIds}
        showPrintBoundary={showPrintBoundary}
        showMinimap={showMinimap}
        onToggleLayer={toggleLayer}
        onTogglePrintBoundary={() => setShowPrintBoundary((value) => !value)}
        onToggleMinimap={() => setShowMinimap((value) => !value)}
        onSelectObject={setSelectedObject}
        onAddSymbol={handleAddSymbol}
      />
      <main className="drawing-workspace__main" aria-label="Drawing workspace">
        <div className="drawing-workspace-view-switch" aria-label="Workspace view">
          <button type="button" className={workspaceView === 'drawing' ? 'is-active' : ''} aria-pressed={workspaceView === 'drawing'} onClick={() => setWorkspaceView('drawing')}>
            P&ID combiner
          </button>
          <button type="button" className={workspaceView === 'tree' ? 'is-active' : ''} aria-pressed={workspaceView === 'tree'} onClick={() => setWorkspaceView('tree')}>
            Tree workbench
          </button>
        </div>
        {workspaceView === 'tree' ? (
          <section className="drawing-tree-workbench" aria-label="Relationship tree workbench">
            <PidRelationshipTree drawing={localDrawing} mode="workbench" onSelectRow={setSelectedTreeRow} />
          </section>
        ) : (
          <section className="drawing-combiner-workbench" aria-label="P&ID combiner workbench">
            <DrawingToolbar
              mode={toolMode}
              objectCount={localDrawing.objects.length}
              selectedLabel={selectedLabel}
              lineDraftActive={lineStart !== null}
              onModeChange={handleModeChange}
              onAddRegion={handleAddRegion}
              onUndo={undo}
              onRedo={redo}
              canUndo={history.past.length > 0}
              canRedo={history.future.length > 0}
              onFitView={() => setFitRequestId((id) => id + 1)}
              showPrintBoundary={showPrintBoundary}
              onTogglePrintBoundary={() => setShowPrintBoundary((value) => !value)}
              hasLineTagRegister={sourceRegisterCount > 0}
              showLineTagRegister={showLineTagRegister}
              onToggleLineTagRegister={() => setShowLineTagRegister((value) => !value)}
              onSave={onSave ? () => void onSave(localDrawingRef.current) : undefined}
              onExportSvg={onExportSvg ? () => void onExportSvg(localDrawingRef.current) : undefined}
              onExportPdf={onExportPdf ? () => void onExportPdf(localDrawingRef.current) : undefined}
            />
            <DrawingCanvas
              drawing={localDrawing}
              selectedId={currentSelectedId}
              mode={toolMode}
              hiddenLayerIds={hiddenLayerIds}
              showPrintBoundary={showPrintBoundary}
              showMinimap={showMinimap}
              fitRequestId={fitRequestId}
              apiBaseUrl={apiBaseUrl}
              onSelectObject={setSelectedObject}
              onMoveObject={(id, dx, dy) => applyAction({ type: 'moveObject', id, dx, dy })}
              onLinePoint={handleLinePoint}
              onCreateTextAt={handleCreateTextAt}
            />
            {showLineTagRegister && sourceRegisterCount > 0 ? (
              <LineTagRegisterDrawer
                lineRows={sourceRegister.lineTags}
                equipmentRows={sourceRegister.equipment}
                onClose={() => setShowLineTagRegister(false)}
              />
            ) : null}
          </section>
        )}
      </main>
      {workspaceView === 'tree' ? (
        <TreeSourceInspector
          row={selectedTreeRow}
          sourcePages={localDrawing.sourcePages}
          projectId={localDrawing.projectId}
          apiBaseUrl={apiBaseUrl}
          documentGuide={electricalDocumentGuide}
          onOpenSource={handleOpenTreeSource}
        />
      ) : (
        <DrawingInspector
          selectedObject={selectedObject}
          sourcePages={localDrawing.sourcePages}
          projectId={localDrawing.projectId}
          apiBaseUrl={apiBaseUrl}
          onOpenSourcePage={handleOpenSourcePage}
          onUpdateLabel={(id, label) => applyAction({ type: 'updateLabel', id, label })}
          onUpdateStyle={(id, style) => applyAction({ type: 'updateObjectStyle', id, style })}
          onUpdateMetadata={(id, metadata) => applyAction({ type: 'updateObjectMetadata', id, metadata })}
          onUpdateBounds={(id, bounds) => applyAction({ type: 'updateObjectBounds', id, bounds })}
          onAddConnectorBend={(id) => applyAction({ type: 'addConnectorBend', id })}
          onDeleteObject={handleDeleteObject}
        />
      )}
      {sourceViewerTarget && apiBaseUrl ? (
        <SourceViewer
          target={sourceViewerTarget}
          apiBaseUrl={apiBaseUrl}
          projectId={localDrawing.projectId}
          onClose={() => setSourceViewerTarget(null)}
        />
      ) : null}
    </div>
  );
}

function sourceViewerTargetForPage(page: PageEvidence, sourcePages: PageEvidence[]): SourceViewerTarget {
  const sameSourcePages = sourcePages.filter((candidate) => candidate.sourceFileId === page.sourceFileId);
  const totalPages = Math.max(page.page, ...sameSourcePages.map((candidate) => candidate.page));
  return {
    sourceFileId: page.sourceFileId,
    sourceFileName: page.sourceFileId,
    page: page.page,
    totalPages,
    bounds: null,
    allEvidence: [],
  };
}

function sourceViewerTargetForTreeRow(row: RelationshipTreeRow, sourcePages: PageEvidence[]): SourceViewerTarget | null {
  if (!row.sourceFileId || row.page === null) {
    return null;
  }
  const sameSourcePages = sourcePages.filter((candidate) => candidate.sourceFileId === row.sourceFileId);
  const totalPages = Math.max(row.page, ...sameSourcePages.map((candidate) => candidate.page));
  const sourceFileName = basename(row.sourcePath) || row.sourceFileId;
  return {
    sourceFileId: row.sourceFileId,
    sourceFileName,
    page: row.page,
    totalPages,
    bounds: row.sourceBounds,
    allEvidence: row.sourceBounds
      ? [
          {
            id: row.id,
            sourceFileId: row.sourceFileId,
            page: row.page,
            bounds: row.sourceBounds,
            text: row.tag,
            confidence: row.confidence ?? 0,
          },
        ]
      : [],
  };
}

function TreeSourceInspector({
  row,
  sourcePages,
  projectId,
  apiBaseUrl,
  documentGuide,
  onOpenSource,
}: {
  row: RelationshipTreeRow | null;
  sourcePages: PageEvidence[];
  projectId: string;
  apiBaseUrl?: string | null;
  documentGuide: ElectricalDocumentGuide | null;
  onOpenSource: (row: RelationshipTreeRow) => void;
}) {
  const sourcePage = row?.sourceFileId && row.page !== null
    ? sourcePages.find((candidate) => candidate.sourceFileId === row.sourceFileId && candidate.page === row.page) ?? null
    : null;
  const sourceName = row ? basename(row.sourcePath) || row.sourceFileId : '';
  const canOpen = Boolean(row && apiBaseUrl && row.sourceFileId && row.page !== null);

  return (
    <aside className="drawing-inspector" aria-label="Tree source inspector">
      <div className="drawing-panel-heading">
        <h2>Tree Source</h2>
      </div>
      {!row ? (
        <p className="drawing-panel-empty">Select a hierarchy row to inspect source evidence.</p>
      ) : (
        <>
          <dl className="drawing-inspector__meta">
            <div>
              <dt>Tag</dt>
              <dd title={row.tag}>{row.tag}</dd>
            </div>
            <div>
              <dt>System</dt>
              <dd>{row.system || '-'}</dd>
            </div>
            <div>
              <dt>Type</dt>
              <dd>{row.kind.replace(/_/g, ' ')}</dd>
            </div>
            <div>
              <dt>Relation</dt>
              <dd>{row.relationship.replace(/_/g, ' ')}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{row.confidence === null ? '-' : `${Math.round(row.confidence * 100)}%`}</dd>
            </div>
          </dl>

          {row.sourceFileId && row.page !== null ? (
            <div className="drawing-inspector__section">
              <h3>Source document</h3>
              <div className="drawing-source-link-card drawing-source-link-card--tree">
                {apiBaseUrl && sourcePage ? (
                  <div className="tree-source-inspector__preview">
                    <img
                      src={sourcePageImageUrl(apiBaseUrl, projectId, sourcePage, 96)}
                      alt={`${sourcePage.sourceFileId} page ${sourcePage.page} source preview`}
                    />
                    {row.sourceBounds ? <span className="tree-source-inspector__highlight" style={sourceThumbnailHighlightStyle(row, sourcePage)} /> : null}
                  </div>
                ) : (
                  <div className="tree-source-inspector__preview-placeholder" aria-hidden="true" />
                )}
                <div>
                  <strong title={sourceName}>{sourceName}</strong>
                  <span>Page {row.page}</span>
                  {sourcePage ? <span>{textExtractionLabel(sourcePage)}</span> : null}
                  <span>{row.sourceBounds ? 'Highlighted bounds available' : 'Page-level evidence'}</span>
                </div>
                <button type="button" disabled={!canOpen} onClick={() => onOpenSource(row)}>
                  View highlighted source
                </button>
              </div>
            </div>
          ) : (
            <p className="drawing-panel-empty">This row is generated by the hierarchy rules and does not map to a single source tag.</p>
          )}
          {documentGuide ? <DocumentGuideTrace guide={documentGuide} sourcePages={sourcePages} projectId={projectId} apiBaseUrl={apiBaseUrl} /> : null}
        </>
      )}
    </aside>
  );
}

function DocumentGuideTrace({
  guide,
  sourcePages,
  projectId,
  apiBaseUrl,
}: {
  guide: ElectricalDocumentGuide;
  sourcePages: PageEvidence[];
  projectId: string;
  apiBaseUrl?: string | null;
}) {
  const guidePageRef = guide.sourcePages.at(0) ?? null;
  const sourcePage = guidePageRef
    ? sourcePages.find((candidate) => candidate.sourceFileId === guidePageRef.sourceFileId && candidate.page === guidePageRef.page) ?? null
    : null;
  const abbreviationRows = Object.entries(guide.abbreviations).slice(0, 6);
  const schema = guide.equipmentTagSchema.map(sentenceCase).join(' -> ');
  return (
    <div className="drawing-inspector__section">
      <h3>Document guide</h3>
      <div className="drawing-source-link-card drawing-source-link-card--tree">
        {apiBaseUrl && sourcePage ? (
          <div className="tree-source-inspector__preview">
            <img
              src={sourcePageImageUrl(apiBaseUrl, projectId, sourcePage, 96)}
              alt={`${sourcePage.sourceFileId} page ${sourcePage.page} document guide preview`}
            />
          </div>
        ) : (
          <div className="tree-source-inspector__preview-placeholder" aria-hidden="true" />
        )}
        <div>
          {guidePageRef ? <strong>Page {guidePageRef.page}</strong> : <strong>Guide sheet</strong>}
          {schema ? <span title={schema}>{schema}</span> : null}
          {abbreviationRows.map(([code, phrase]) => (
            <span key={code}>{code}: {sentenceCase(phrase)}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function sourcePageImageUrl(apiBaseUrl: string, projectId: string, page: PageEvidence, dpi: number): string {
  return `${apiBaseUrl}/projects/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(page.sourceFileId)}/pages/${page.page}/image?dpi=${dpi}`;
}

interface ElectricalDocumentGuide {
  sourcePages: Array<{ sourceFileId: string; page: number; pageId: string }>;
  abbreviations: Record<string, string>;
  equipmentTagSchema: string[];
}

function readElectricalDocumentGuide(visualQa: Record<string, unknown>): ElectricalDocumentGuide | null {
  const electricalGraph = visualQa.electricalRelationshipGraph && typeof visualQa.electricalRelationshipGraph === 'object'
    ? (visualQa.electricalRelationshipGraph as Record<string, unknown>)
    : null;
  const metrics = electricalGraph?.metrics && typeof electricalGraph.metrics === 'object'
    ? (electricalGraph.metrics as Record<string, unknown>)
    : null;
  const guide = metrics?.documentGuide && typeof metrics.documentGuide === 'object'
    ? (metrics.documentGuide as Record<string, unknown>)
    : null;
  if (!guide) {
    return null;
  }
  const sourcePages = Array.isArray(guide.sourcePages)
    ? guide.sourcePages
        .map((value): ElectricalDocumentGuide['sourcePages'][number] | null => {
          if (!value || typeof value !== 'object') {
            return null;
          }
          const row = value as Record<string, unknown>;
          const sourceFileId = typeof row.sourceFileId === 'string' ? row.sourceFileId : '';
          const page = typeof row.page === 'number' && Number.isFinite(row.page) ? row.page : null;
          if (!sourceFileId || page === null) {
            return null;
          }
          return {
            sourceFileId,
            page,
            pageId: typeof row.pageId === 'string' ? row.pageId : '',
          };
        })
        .filter((value): value is ElectricalDocumentGuide['sourcePages'][number] => value !== null)
    : [];
  const abbreviations = guide.abbreviations && typeof guide.abbreviations === 'object'
    ? Object.fromEntries(
        Object.entries(guide.abbreviations as Record<string, unknown>)
          .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].trim().length > 0),
      )
    : {};
  const equipmentTagSchema = Array.isArray(guide.equipmentTagSchema)
    ? guide.equipmentTagSchema.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    : [];
  if (sourcePages.length === 0 && Object.keys(abbreviations).length === 0 && equipmentTagSchema.length === 0) {
    return null;
  }
  return { sourcePages, abbreviations, equipmentTagSchema };
}

function sentenceCase(value: string): string {
  const lower = value.toLowerCase();
  return lower.replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function sourceThumbnailHighlightStyle(row: RelationshipTreeRow, page: PageEvidence): CSSProperties {
  const bounds = row.sourceBounds;
  if (!bounds || page.width <= 0 || page.height <= 0) {
    return {};
  }
  return {
    left: `${(bounds.x / page.width) * 100}%`,
    top: `${(bounds.y / page.height) * 100}%`,
    width: `${(bounds.width / page.width) * 100}%`,
    height: `${(bounds.height / page.height) * 100}%`,
  };
}

function textExtractionLabel(page: PageEvidence): string {
  const extraction = page.metadata && typeof page.metadata === 'object' ? page.metadata.textExtraction : null;
  if (!extraction || typeof extraction !== 'object') {
    return 'Native PDF text';
  }
  const mode = (extraction as Record<string, unknown>).mode;
  if (mode === 'native+ocr') {
    return 'Native text + OCR fallback';
  }
  if (mode === 'ocr_unavailable') {
    return 'OCR fallback unavailable';
  }
  if (mode === 'ocr_empty') {
    return 'OCR fallback found no text';
  }
  return 'Native PDF text';
}

function basename(path: string): string {
  if (!path) {
    return '';
  }
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) ?? path;
}

interface LineTagRegisterRow {
  tag: string;
  system: string;
  status: string;
  sourcePages: number;
}

interface EquipmentRegisterRow extends LineTagRegisterRow {
  section: string;
}

function readSourceRegister(visualQa: Record<string, unknown>): { lineTags: LineTagRegisterRow[]; equipment: EquipmentRegisterRow[] } {
  return {
    lineTags: readRegisterRows(visualQa.lineTagRegister),
    equipment: readRegisterRows(visualQa.equipmentRegister).map((row, index) => {
      const source = Array.isArray(visualQa.equipmentRegister) ? visualQa.equipmentRegister[index] : null;
      const sourceRow = source && typeof source === 'object' ? (source as Record<string, unknown>) : {};
      return {
        ...row,
        section: typeof sourceRow.section === 'string' ? sourceRow.section : 'Equipment register',
      };
    }),
  };
}

function readRegisterRows(value: unknown): LineTagRegisterRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item): LineTagRegisterRow | null => {
      if (!item || typeof item !== 'object') {
        return null;
      }
      const row = item as Record<string, unknown>;
      const tag = typeof row.tag === 'string' ? row.tag : '';
      if (!tag.trim()) {
        return null;
      }
      return {
        tag,
        system: typeof row.system === 'string' ? row.system : 'DEFAULT',
        status: typeof row.status === 'string' ? row.status : 'registered',
        sourcePages: typeof row.sourcePages === 'number' && Number.isFinite(row.sourcePages) ? row.sourcePages : 0,
      };
    })
    .filter((item): item is LineTagRegisterRow => item !== null);
}

function LineTagRegisterDrawer({
  lineRows,
  equipmentRows,
  onClose,
}: {
  lineRows: LineTagRegisterRow[];
  equipmentRows: EquipmentRegisterRow[];
  onClose: () => void;
}) {
  const shownLineRows = lineRows.slice(0, 160);
  const shownEquipmentRows = equipmentRows.slice(0, 160);
  const totalRows = lineRows.length + equipmentRows.length;
  return (
    <section className="line-tag-register-drawer" role="region" aria-label="Line tag register">
      <header className="line-tag-register-drawer__header">
        <div>
          <strong>Source Register</strong>
          <span>{totalRows} extracted items held outside the final drawing</span>
        </div>
        <button type="button" onClick={onClose} title="Close line tag register">
          Close
        </button>
      </header>
      {shownEquipmentRows.length > 0 ? (
        <RegisterTable title="Staged equipment" rows={shownEquipmentRows} showSection />
      ) : null}
      {shownLineRows.length > 0 ? <RegisterTable title="Line tags" rows={shownLineRows} /> : null}
    </section>
  );
}

function RegisterTable({
  title,
  rows,
  showSection = false,
}: {
  title: string;
  rows: Array<LineTagRegisterRow | EquipmentRegisterRow>;
  showSection?: boolean;
}) {
  return (
    <div className="line-tag-register-drawer__table" role="table" aria-label={title}>
      <div className="line-tag-register-drawer__caption">{title}</div>
      <div className="line-tag-register-drawer__row line-tag-register-drawer__row--head" role="row">
        <span role="columnheader">Tag</span>
        <span role="columnheader">System</span>
        <span role="columnheader">{showSection ? 'Section' : 'Status'}</span>
        <span role="columnheader">Pages</span>
      </div>
      {rows.map((row) => (
        <div className="line-tag-register-drawer__row" role="row" key={`${title}:${row.system}:${row.tag}`}>
          <span role="cell">{row.tag}</span>
          <span role="cell">{row.system}</span>
          <span role="cell">{showSection && 'section' in row ? row.section : row.status}</span>
          <span role="cell">{row.sourcePages || '-'}</span>
        </div>
      ))}
    </div>
  );
}

interface LineDraftStart {
  point: DrawingPoint;
  objectId: string | null;
}

function createDefaultRegion(drawing: DrawingDocument): DrawingObject {
  const regionCount = drawing.objects.filter((object) => object.kind === 'region').length;
  const id = nextRegionId(drawing, regionCount + 1);
  const bounds = defaultRegionBounds(drawing, regionCount);

  return {
    id,
    kind: 'region',
    label: `Region ${regionCount + 1}`,
    points: [
      { x: bounds.x, y: bounds.y },
      { x: bounds.x + bounds.width, y: bounds.y + bounds.height },
    ],
    bounds,
    style: {
      stroke: '#0284c7',
      fill: 'rgba(14, 165, 233, 0.14)',
      strokeWidth: 1.5,
      opacity: 1,
    },
    sourceEvidenceIds: [],
  };
}

function createDefaultTextBox(drawing: DrawingDocument, point: DrawingPoint): DrawingObject {
  const textCount = drawing.objects.filter((object) => object.kind === 'label' && object.metadata?.textBox === true).length;
  const id = nextObjectId(drawing, 'text', textCount + 1);
  const width = 180;
  const height = 34;
  const bounds = {
    x: clamp(point.x - width / 2, 8, Math.max(8, finitePositive(drawing.width, 1200) - width - 8)),
    y: clamp(point.y - height / 2, 8, Math.max(8, finitePositive(drawing.height, 800) - height - 8)),
    width,
    height,
  };

  return {
    id,
    kind: 'label',
    label: 'Text note',
    points: [
      { x: bounds.x, y: bounds.y },
      { x: bounds.x + bounds.width, y: bounds.y + bounds.height },
    ],
    bounds,
    style: {
      stroke: '#0f172a',
      fill: '#ffffff',
      strokeWidth: 1,
      opacity: 1,
      fontSize: 14,
      fontFamily: 'Arial',
    },
    sourceEvidenceIds: [],
    metadata: {
      textBox: true,
      textAlign: 'left',
      fontWeight: '800',
      fontStyle: 'normal',
      boxStroke: '#cbd5e1',
    },
  };
}

function createDefaultSymbol(drawing: DrawingDocument, symbolType: string): DrawingObject {
  const symbolCount = drawing.objects.filter((object) => object.kind === 'symbol' && object.metadata?.userPlacedSymbol === true).length;
  const id = nextObjectId(drawing, 'symbol', symbolCount + 1);
  const label = humanizeSymbolType(symbolType);
  const width = defaultSymbolWidth(symbolType);
  const height = defaultSymbolHeight(symbolType);
  const bounds = {
    x: clamp(finitePositive(drawing.width, 1200) * 0.5 - width * 0.5 + symbolCount * 12, 12, Math.max(12, finitePositive(drawing.width, 1200) - width - 12)),
    y: clamp(finitePositive(drawing.height, 800) * 0.5 - height * 0.5 + symbolCount * 10, 12, Math.max(12, finitePositive(drawing.height, 800) - height - 12)),
    width,
    height,
  };

  return {
    id,
    kind: 'symbol',
    label,
    points: [
      { x: bounds.x, y: bounds.y },
      { x: bounds.x + bounds.width, y: bounds.y + bounds.height },
    ],
    bounds,
    style: {
      stroke: '#111827',
      fill: '#ffffff',
      strokeWidth: 1.25,
      opacity: 1,
    },
    sourceEvidenceIds: [],
    metadata: {
      userPlacedSymbol: true,
      symbolRegistry: 'recreation-vector-pack',
      symbolType,
      hideCenterLabel: false,
    },
  };
}

function createDefaultConnector(drawing: DrawingDocument, start: LineDraftStart, end: LineDraftStart): DrawingObject {
  const connectorCount = drawing.objects.filter((object) => object.kind === 'connector' || object.kind === 'pipe').length;
  const id = nextObjectId(drawing, 'connector', connectorCount + 1);
  const points = routeOrthogonal(start.point, end.point);

  return {
    id,
    kind: 'connector',
    label: '',
    points,
    bounds: boundsForPoints(points),
    style: {
      stroke: '#0f172a',
      fill: 'transparent',
      strokeWidth: 2,
      opacity: 1,
    },
    sourceEvidenceIds: [],
    metadata: {
      userCreated: true,
      startObjectId: start.objectId ?? undefined,
      endObjectId: end.objectId ?? undefined,
    },
  };
}

function nextRegionId(drawing: DrawingDocument, startIndex: number): string {
  return nextObjectId(drawing, 'region', startIndex);
}

function nextObjectId(drawing: DrawingDocument, prefix: string, startIndex: number): string {
  const ids = new Set(drawing.objects.map((object) => object.id));
  let index = startIndex;
  let id = `${prefix}-${index}`;
  while (ids.has(id)) {
    index += 1;
    id = `${prefix}-${index}`;
  }
  return id;
}

function boundsForPoints(points: DrawingPoint[]): DrawingBounds {
  const finite = points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (finite.length === 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }
  const xs = finite.map((point) => point.x);
  const ys = finite.map((point) => point.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y };
}

function defaultRegionBounds(drawing: DrawingDocument, regionCount: number): DrawingBounds {
  const width = finitePositive(drawing.width, 1200);
  const height = finitePositive(drawing.height, 800);
  const regionWidth = Math.min(Math.max(width * 0.18, 160), Math.max(48, width - 32));
  const regionHeight = Math.min(Math.max(height * 0.12, 96), Math.max(40, height - 32));
  const offset = (regionCount % 6) * 18;

  return {
    x: clamp(width * 0.5 - regionWidth * 0.5 + offset, 16, Math.max(16, width - regionWidth - 16)),
    y: clamp(height * 0.5 - regionHeight * 0.5 + offset, 16, Math.max(16, height - regionHeight - 16)),
    width: regionWidth,
    height: regionHeight,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function finitePositive(value: number, fallback: number): number {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function humanizeSymbolType(type: string): string {
  return type
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function defaultSymbolWidth(symbolType: string): number {
  if (symbolType === 'offpage' || symbolType === 'flow_arrow') {
    return 84;
  }
  if (symbolType === 'instrument' || symbolType === 'gauge') {
    return 42;
  }
  return 62;
}

function defaultSymbolHeight(symbolType: string): number {
  if (symbolType === 'offpage' || symbolType === 'flow_arrow') {
    return 34;
  }
  if (symbolType === 'valve' || symbolType.endsWith('_valve') || symbolType === 'reducer') {
    return 36;
  }
  return 48;
}
