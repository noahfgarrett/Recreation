import { useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent, type KeyboardEvent, type MouseEvent } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { Bounds, DrawingDocument } from '../../types';

export interface RelationshipTreeRow {
  id: string;
  depth: number;
  tag: string;
  equipmentDescription: string;
  kind: string;
  system: string;
  relationship: string;
  parentTag: string;
  sourceFileId: string;
  page: number | null;
  sourcePath: string;
  sourceBounds: Bounds | null;
  status: string;
  confidence: number | null;
  targetTag?: string;
  targetEquipmentDescription?: string;
  targetDiscipline?: string;
  dependsOnTag?: string;
  dependsOnDescription?: string;
  dependencyDiscipline?: string;
  dependencyType?: string;
  dependencyPath?: string;
  commissioningUse?: string;
  ruleId?: string;
  sourceDiscipline?: string;
  sourceFile?: string;
  sourcePage?: number | null;
  evidenceText?: string;
  notes?: string;
}

interface RelationshipGraphNode {
  id: string;
  kind: string;
  tag: string;
  system?: string;
  sourceFileId?: string;
  page?: number;
  confidence?: number;
  sourcePath?: string;
  sourceBounds?: Bounds | null;
  discipline?: string;
  equipmentDescription?: string;
  metadata?: Record<string, unknown>;
}

interface RelationshipGraphEdge {
  id: string;
  kind: string;
  sourceId: string;
  targetId: string;
  sourceTag?: string;
  targetTag?: string;
  label?: string;
  lineTag?: string;
  system?: string;
  status?: string;
  confidence?: number;
  ruleId?: string;
  sourceEvidenceIds?: string[];
  metadata?: Record<string, unknown>;
}

interface RelationshipGraphPayload {
  nodes: RelationshipGraphNode[];
  edges: RelationshipGraphEdge[];
}

interface SharedHierarchyGraph {
  graph: RelationshipGraphPayload;
  id: string;
  discipline: string;
}

interface PidRelationshipTreeProps {
  drawing: DrawingDocument;
  onSelectRow?: (row: RelationshipTreeRow) => void;
}

const TREE_COLUMNS = ['Smartsheet Primary', 'Level', 'Tag', 'Equipment Description', 'Kind', 'System', 'Relationship', 'Parent', 'Source', 'Page', 'Source Path', 'Source Bounds', 'Status', 'Confidence'];
const DEPENDENCY_COLUMNS = ['Target Equipment Tag', 'Target Equipment Description', 'Target Discipline', 'Depends On Equipment Tag', 'Depends On Description', 'Dependency Discipline', 'Dependency Type', 'Status', 'Confidence', 'Dependency Path', 'Commissioning Use', 'Rule ID', 'Source Discipline', 'Source File', 'Source Page', 'Evidence Text', 'Notes'];
const TREE_ZOOM_STEP = 0.1;
const TREE_ZOOM_MIN = 0.8;
const TREE_ZOOM_MAX = 1.5;
const TREE_PARENT_EDGE_KINDS = new Set([
  'attached_to_line',
  'instrument_on_line',
  'device_on_line',
  'device_on_equipment',
  'equipment_component',
  'equipment_on_section',
  'feeds_panel',
  'panel_schedule_feeds',
  'panel_circuit',
  'continuation_on_line',
  'represents_instance',
  'control_panel_for',
  'control_point_on_panel',
  'instrument_on_equipment',
  'line_mounted_item',
  'process_flow',
]);

type RelationshipTreeMode = 'compact' | 'workbench';
type RelationshipTreeViewMode = 'full' | 'equipment' | 'dependency';
type DependencyStatusFilter = 'confirmed' | 'inferred' | 'needs_review';

interface BuildRelationshipTreeOptions {
  viewMode?: RelationshipTreeViewMode;
  dependencyStatuses?: Iterable<string>;
}

interface MarqueeState {
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
  active: boolean;
}

export function PidRelationshipTree({ drawing, onSelectRow, mode = 'compact' }: PidRelationshipTreeProps & { mode?: RelationshipTreeMode }) {
  const supportsEquipmentFlow = useMemo(() => hasElectricalRelationshipGraph(drawing), [drawing]);
  const supportsDependencyView = useMemo(() => hasDependencyGraph(drawing), [drawing]);
  const [viewMode, setViewMode] = useState<RelationshipTreeViewMode>(() => defaultRelationshipViewMode(drawing));
  const [dependencyStatuses, setDependencyStatuses] = useState<Set<DependencyStatusFilter>>(() => new Set(['confirmed', 'inferred', 'needs_review']));
  const dependencyStatusKey = useMemo(() => [...dependencyStatuses].sort().join('|'), [dependencyStatuses]);
  const generatedRows = useMemo(
    () => buildRelationshipTreeRows(drawing, { viewMode, dependencyStatuses }),
    [drawing, viewMode, dependencyStatusKey],
  );
  const [editableRows, setEditableRows] = useState(generatedRows);
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [primarySelectedRowId, setPrimarySelectedRowId] = useState<string | null>(null);
  const [anchorRowId, setAnchorRowId] = useState<string | null>(null);
  const [dragRowId, setDragRowId] = useState<string | null>(null);
  const [marquee, setMarquee] = useState<MarqueeState | null>(null);
  const [treeZoom, setTreeZoom] = useState(1);
  const [collapsedRowIds, setCollapsedRowIds] = useState<Set<string>>(new Set());
  const rowContainerRef = useRef<HTMLDivElement | null>(null);
  const rowElementRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const rows = mode === 'workbench' ? editableRows : generatedRows;
  const expandableRowIds = useMemo(() => expandableRelationshipRowIds(rows), [rows]);
  const visibleRows = useMemo(() => visibleRelationshipRows(rows, collapsedRowIds), [rows, collapsedRowIds]);
  const activeCollapsedRowCount = useMemo(() => [...collapsedRowIds].filter((rowId) => expandableRowIds.has(rowId)).length, [collapsedRowIds, expandableRowIds]);
  const fileStem = sanitizeFileStem(`${drawing.name || drawing.id}-${viewMode === 'dependency' ? 'dependency-view' : 'relationship-tree'}`);
  const selectedIndex = primarySelectedRowId ? rows.findIndex((row) => row.id === primarySelectedRowId) : -1;
  const selectedRow = selectedIndex >= 0 ? rows[selectedIndex] : null;
  const selectedRows = rows.filter((row) => selectedRowIds.has(row.id));
  const renderedRows = mode === 'workbench' ? visibleRows : visibleRows.slice(0, 180);
  const rowCountLabel = visibleRows.length === rows.length ? `${rows.length} rows` : `${visibleRows.length} / ${rows.length} visible`;

  useEffect(() => {
    setEditableRows(generatedRows);
    setSelectedRowIds(new Set());
    setPrimarySelectedRowId(null);
    setAnchorRowId(null);
    setDragRowId(null);
    setMarquee(null);
  }, [generatedRows]);

  useEffect(() => {
    setCollapsedRowIds(new Set());
  }, [drawing.id]);

  useEffect(() => {
    setViewMode(supportsEquipmentFlow ? 'equipment' : supportsDependencyView ? 'dependency' : 'full');
    setDependencyStatuses(new Set(['confirmed', 'inferred', 'needs_review']));
  }, [drawing.id, supportsEquipmentFlow, supportsDependencyView]);

  const toggleDependencyStatus = (status: DependencyStatusFilter) => {
    setDependencyStatuses((current) => {
      const next = new Set(current);
      if (next.has(status)) {
        next.delete(status);
      } else {
        next.add(status);
      }
      return next;
    });
  };

  const updateSelectedDepth = (delta: number) => {
    if (selectedRowIds.size === 0) {
      return;
    }
    setEditableRows((current) => {
      let changed = false;
      const next = current.map((row) => {
        if (!selectedRowIds.has(row.id)) {
          return row;
        }
        const nextDepth = Math.max(0, Math.min(12, row.depth + delta));
        if (nextDepth === row.depth) {
          return row;
        }
        changed = true;
        return { ...row, depth: nextDepth, relationship: delta > 0 ? 'manual indent' : 'manual outdent' };
      });
      if (!changed) {
        return current;
      }
      return next;
    });
  };

  const moveSelected = (delta: number) => {
    if (selectedRowIds.size === 0) {
      return;
    }
    setEditableRows((current) => moveSelectedRows(current, selectedRowIds, delta));
  };

  const handleRowKeyDown = (event: KeyboardEvent<HTMLDivElement>, rowId: string) => {
    const row = rows.find((candidate) => candidate.id === rowId);
    if (row) {
      if (!selectedRowIds.has(rowId)) {
        setSelection(new Set([rowId]), rowId);
      }
      onSelectRow?.(row);
    }
    if (event.key === 'Tab') {
      event.preventDefault();
      updateSelectedDepth(event.shiftKey ? -1 : 1);
    }
    if ((event.metaKey || event.ctrlKey) && event.key === 'ArrowUp') {
      event.preventDefault();
      moveSelected(-1);
    }
    if ((event.metaKey || event.ctrlKey) && event.key === 'ArrowDown') {
      event.preventDefault();
      moveSelected(1);
    }
  };

  const setSelection = (nextSelection: Set<string>, primaryRowId: string | null) => {
    setSelectedRowIds(nextSelection);
    setPrimarySelectedRowId(primaryRowId);
    setAnchorRowId(primaryRowId);
  };

  const handleRowClick = (event: MouseEvent<HTMLDivElement>, row: RelationshipTreeRow, rowIndex: number) => {
    if (mode !== 'workbench') {
      return;
    }
    let nextSelection = new Set<string>();
    if (event.shiftKey && anchorRowId) {
      const anchorIndex = rows.findIndex((candidate) => candidate.id === anchorRowId);
      if (anchorIndex >= 0) {
        const start = Math.min(anchorIndex, rowIndex);
        const end = Math.max(anchorIndex, rowIndex);
        nextSelection = new Set(rows.slice(start, end + 1).map((candidate) => candidate.id));
      } else {
        nextSelection.add(row.id);
      }
      setSelectedRowIds(nextSelection);
      setPrimarySelectedRowId(row.id);
    } else if (event.metaKey || event.ctrlKey) {
      setSelectedRowIds((current) => {
        nextSelection = new Set(current);
        if (nextSelection.has(row.id)) {
          nextSelection.delete(row.id);
        } else {
          nextSelection.add(row.id);
        }
        setPrimarySelectedRowId(nextSelection.has(row.id) ? row.id : [...nextSelection].at(-1) ?? null);
        return nextSelection;
      });
      setAnchorRowId(row.id);
    } else {
      setSelection(new Set([row.id]), row.id);
    }
    onSelectRow?.(row);
  };

  const handleRowsMouseDown = (event: MouseEvent<HTMLDivElement>) => {
    if (mode !== 'workbench' || event.button !== 0) {
      return;
    }
    setMarquee({
      startX: event.clientX,
      startY: event.clientY,
      currentX: event.clientX,
      currentY: event.clientY,
      active: false,
    });
  };

  const handleRowsMouseMove = (event: MouseEvent<HTMLDivElement>) => {
    if (!marquee) {
      return;
    }
    const dx = Math.abs(event.clientX - marquee.startX);
    const dy = Math.abs(event.clientY - marquee.startY);
    const nextMarquee = {
      ...marquee,
      currentX: event.clientX,
      currentY: event.clientY,
      active: marquee.active || dx > 6 || dy > 6,
    };
    setMarquee(nextMarquee);
    if (!nextMarquee.active) {
      return;
    }
    const selectionBounds = marqueeBounds(nextMarquee);
    const intersecting = rows.filter((row) => {
      const element = rowElementRefs.current.get(row.id);
      return element ? rectanglesIntersect(selectionBounds, element.getBoundingClientRect()) : false;
    });
    const nextSelection = new Set(intersecting.map((row) => row.id));
    setSelectedRowIds(nextSelection);
    setPrimarySelectedRowId(intersecting.at(-1)?.id ?? null);
  };

  const handleRowsMouseUp = () => {
    if (marquee?.active) {
      setAnchorRowId(primarySelectedRowId);
    }
    setMarquee(null);
  };

  const handleRowsMouseLeave = () => {
    setMarquee(null);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>, targetRowId: string) => {
    event.preventDefault();
    if (!dragRowId || dragRowId === targetRowId) {
      return;
    }
    setEditableRows((current) => {
      const movingIds = selectedRowIds.has(dragRowId) ? selectedRowIds : new Set([dragRowId]);
      const to = current.findIndex((row) => row.id === targetRowId);
      return moveRowsToIndex(current, movingIds, to);
    });
    setDragRowId(null);
  };

  const handleDragStart = (rowId: string) => {
    if (!selectedRowIds.has(rowId)) {
      setSelection(new Set([rowId]), rowId);
    }
    setDragRowId(rowId);
  };

  const adjustTreeZoom = (delta: number) => {
    setTreeZoom((current) => clampTreeZoom(current + delta));
  };

  const toggleCollapsedRow = (rowId: string) => {
    setCollapsedRowIds((current) => {
      const next = new Set(current);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  };

  return (
    <div className={`pid-relationship-tree pid-relationship-tree--${mode}`}>
      <div className="pid-relationship-tree__toolbar">
        <span>{rowCountLabel}{mode === 'workbench' && selectedRowIds.size > 1 ? ` / ${selectedRowIds.size} selected` : ''}</span>
        {mode === 'workbench' && (supportsEquipmentFlow || supportsDependencyView) ? (
          <div className="pid-relationship-tree__view-actions" aria-label="Hierarchy view mode">
            {supportsEquipmentFlow ? (
              <button type="button" className={viewMode === 'equipment' ? 'is-active' : ''} aria-pressed={viewMode === 'equipment'} onClick={() => setViewMode('equipment')}>
                Equipment Flow
              </button>
            ) : null}
            <button type="button" className={viewMode === 'full' ? 'is-active' : ''} aria-pressed={viewMode === 'full'} onClick={() => setViewMode('full')}>
              Full Graph
            </button>
            {supportsDependencyView ? (
              <button type="button" className={viewMode === 'dependency' ? 'is-active' : ''} aria-pressed={viewMode === 'dependency'} onClick={() => setViewMode('dependency')}>
                Dependency View
              </button>
            ) : null}
          </div>
        ) : null}
        {mode === 'workbench' && viewMode === 'dependency' ? (
          <div className="pid-relationship-tree__status-filters" aria-label="Dependency status filters">
            {(['confirmed', 'inferred', 'needs_review'] as const).map((status) => (
              <label key={status}>
                <input type="checkbox" checked={dependencyStatuses.has(status)} onChange={() => toggleDependencyStatus(status)} />
                {humanizeStatus(status)}
              </label>
            ))}
          </div>
        ) : null}
        {mode === 'workbench' ? (
          <div className="pid-relationship-tree__branch-actions" aria-label="Branch visibility controls">
            <button type="button" onClick={() => setCollapsedRowIds(new Set())} disabled={activeCollapsedRowCount === 0} aria-label="Expand all branches">
              Expand all
            </button>
            <button type="button" onClick={() => setCollapsedRowIds(new Set(expandableRowIds))} disabled={expandableRowIds.size === 0} aria-label="Collapse all branches">
              Collapse all
            </button>
          </div>
        ) : null}
        {mode === 'workbench' ? (
          <div className="pid-relationship-tree__edit-actions" aria-label="Tree edit actions">
            <button type="button" onClick={() => moveSelected(-1)} disabled={selectedRows.length === 0 || selectedRows.some((row) => rows.indexOf(row) === 0)} aria-label="Move up">
              Up
            </button>
            <button type="button" onClick={() => moveSelected(1)} disabled={selectedRows.length === 0 || selectedRows.some((row) => rows.indexOf(row) === rows.length - 1)} aria-label="Move down">
              Down
            </button>
            <button type="button" onClick={() => updateSelectedDepth(1)} disabled={selectedRows.length === 0} aria-label="Indent">
              Indent
            </button>
            <button type="button" onClick={() => updateSelectedDepth(-1)} disabled={selectedRows.length === 0 || selectedRows.every((row) => row.depth === 0)} aria-label="Outdent">
              Outdent
            </button>
          </div>
        ) : null}
        {mode === 'workbench' ? (
          <div className="pid-relationship-tree__zoom-actions" aria-label="Tree zoom controls">
            <button type="button" onClick={() => adjustTreeZoom(-TREE_ZOOM_STEP)} disabled={treeZoom <= TREE_ZOOM_MIN} aria-label="Zoom tree out">
              -
            </button>
            <button type="button" onClick={() => setTreeZoom(1)} aria-label="Reset tree zoom">
              {Math.round(treeZoom * 100)}%
            </button>
            <button type="button" onClick={() => adjustTreeZoom(TREE_ZOOM_STEP)} disabled={treeZoom >= TREE_ZOOM_MAX} aria-label="Zoom tree in">
              +
            </button>
          </div>
        ) : null}
        {viewMode === 'dependency' ? (
          <button type="button" onClick={() => downloadRelationshipJson(rows, `${fileStem}.json`)} disabled={rows.length === 0}>
            JSON
          </button>
        ) : null}
        <button type="button" onClick={() => downloadRelationshipCsv(rows, `${fileStem}.csv`)} disabled={rows.length === 0}>
          CSV
        </button>
        <button type="button" onClick={() => downloadRelationshipXlsx(rows, `${fileStem}.xlsx`)} disabled={rows.length === 0}>
          XLSX
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="drawing-panel-empty">No relationship graph found for this drawing yet.</p>
      ) : (
        <div
          className="pid-relationship-tree__rows"
          role="tree"
          aria-label="P&ID relationship tree"
          ref={rowContainerRef}
          style={{ '--tree-zoom': formatTreeZoom(treeZoom) } as CSSProperties}
          onMouseDown={handleRowsMouseDown}
          onMouseMove={handleRowsMouseMove}
          onMouseUp={handleRowsMouseUp}
          onMouseLeave={handleRowsMouseLeave}
        >
          {renderedRows.map((row) => {
            const rowIndex = rows.findIndex((candidate) => candidate.id === row.id);
            const isExpandable = expandableRowIds.has(row.id);
            const isCollapsed = collapsedRowIds.has(row.id);
            return (
              <div
                key={`${row.id}:${rowIndex}`}
                ref={(element) => {
                  if (element) {
                    rowElementRefs.current.set(row.id, element);
                  } else {
                    rowElementRefs.current.delete(row.id);
                  }
                }}
                className={`pid-relationship-tree__row${selectedRowIds.has(row.id) ? ' pid-relationship-tree__row--selected' : ''}`}
                role="treeitem"
                aria-level={row.depth + 1}
                aria-selected={selectedRowIds.has(row.id)}
                aria-expanded={isExpandable ? !isCollapsed : undefined}
                title={treeRowTitle(row)}
                tabIndex={mode === 'workbench' ? 0 : undefined}
                draggable={mode === 'workbench'}
                onClick={mode === 'workbench' ? (event) => handleRowClick(event, row, rowIndex) : undefined}
                onKeyDown={mode === 'workbench' ? (event) => handleRowKeyDown(event, row.id) : undefined}
                onDragStart={mode === 'workbench' ? () => handleDragStart(row.id) : undefined}
                onDragOver={mode === 'workbench' ? (event) => event.preventDefault() : undefined}
                onDrop={mode === 'workbench' ? (event) => handleDrop(event, row.id) : undefined}
              >
                <span className="pid-relationship-tree__tag" style={{ '--tree-depth': row.depth } as CSSProperties}>
                  {isExpandable ? (
                    <button
                      type="button"
                      className="pid-relationship-tree__branch-toggle"
                      aria-label={`${isCollapsed ? 'Expand' : 'Collapse'} ${row.tag} branch`}
                      aria-expanded={!isCollapsed}
                      onMouseDown={(event) => event.stopPropagation()}
                      onClick={(event) => {
                        event.stopPropagation();
                        toggleCollapsedRow(row.id);
                      }}
                    >
                      {isCollapsed ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                    </button>
                  ) : (
                    <span className="pid-relationship-tree__branch-spacer" aria-hidden="true" />
                  )}
                  <span className="pid-relationship-tree__tag-text">{row.tag}</span>
                </span>
                <span className="pid-relationship-tree__description">
                  {row.equipmentDescription || '-'}
                </span>
                <span>{humanizeKind(row.relationship)}</span>
                <span
                  className={`pid-relationship-tree__confidence pid-relationship-tree__confidence--${confidenceLevel(row.confidence)}`}
                  aria-label={`Confidence ${confidenceLabel(row.confidence)}`}
                  title={row.confidence === null ? 'Generated grouping row' : `Extraction confidence ${confidenceLabel(row.confidence)}`}
                  style={{ '--confidence-score': confidenceScore(row.confidence) } as CSSProperties}
                >
                  <span aria-hidden="true" />
                  <b>{confidenceLabel(row.confidence)}</b>
                </span>
                {viewMode === 'dependency' ? (
                  <span className={`pid-relationship-tree__status pid-relationship-tree__status--${statusClass(row.status)}`}>
                    {humanizeStatus(row.status)}
                  </span>
                ) : (
                  <b>{row.system || '-'}</b>
                )}
              </div>
            );
          })}
          {marquee?.active ? <span className="pid-relationship-tree__marquee" style={marqueeStyle(marquee, rowContainerRef.current)} aria-hidden="true" /> : null}
        </div>
      )}
    </div>
  );
}

function moveRow(rows: RelationshipTreeRow[], from: number, to: number): RelationshipTreeRow[] {
  if (from < 0 || from >= rows.length || to < 0 || to >= rows.length || from === to) {
    return rows;
  }
  const next = [...rows];
  const [row] = next.splice(from, 1);
  next.splice(to, 0, row);
  return next;
}

function moveSelectedRows(rows: RelationshipTreeRow[], selectedIds: Set<string>, delta: number): RelationshipTreeRow[] {
  if (selectedIds.size === 0 || delta === 0) {
    return rows;
  }
  const selectedIndexes = rows.map((row, index) => (selectedIds.has(row.id) ? index : -1)).filter((index) => index >= 0);
  if (selectedIndexes.length === 0) {
    return rows;
  }
  if (delta < 0) {
    const firstSelected = selectedIndexes[0];
    if (firstSelected === 0) {
      return rows;
    }
    const beforeIndex = firstSelected - 1;
    if (selectedIds.has(rows[beforeIndex].id)) {
      return rows;
    }
    const next = [...rows];
    const [before] = next.splice(beforeIndex, 1);
    next.splice(selectedIndexes[selectedIndexes.length - 1], 0, before);
    return next;
  }
  const lastSelected = selectedIndexes[selectedIndexes.length - 1];
  if (lastSelected >= rows.length - 1) {
    return rows;
  }
  const afterIndex = lastSelected + 1;
  if (selectedIds.has(rows[afterIndex].id)) {
    return rows;
  }
  const next = [...rows];
  const [after] = next.splice(afterIndex, 1);
  next.splice(selectedIndexes[0], 0, after);
  return next;
}

function moveRowsToIndex(rows: RelationshipTreeRow[], selectedIds: Set<string>, targetIndex: number): RelationshipTreeRow[] {
  if (selectedIds.size === 0 || targetIndex < 0 || targetIndex >= rows.length) {
    return rows;
  }
  const moving = rows.filter((row) => selectedIds.has(row.id));
  if (moving.length === 0 || selectedIds.has(rows[targetIndex].id)) {
    return rows;
  }
  const stationaryBeforeTarget = rows.slice(0, targetIndex).filter((row) => !selectedIds.has(row.id)).length;
  const stationary = rows.filter((row) => !selectedIds.has(row.id));
  const next = [...stationary];
  next.splice(stationaryBeforeTarget, 0, ...moving);
  return next;
}

function marqueeBounds(marquee: MarqueeState): DOMRectLike {
  const left = Math.min(marquee.startX, marquee.currentX);
  const top = Math.min(marquee.startY, marquee.currentY);
  const right = Math.max(marquee.startX, marquee.currentX);
  const bottom = Math.max(marquee.startY, marquee.currentY);
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function marqueeStyle(marquee: MarqueeState, container: HTMLElement | null): CSSProperties {
  const bounds = marqueeBounds(marquee);
  const containerBounds = container?.getBoundingClientRect();
  const offsetX = containerBounds?.left ?? 0;
  const offsetY = containerBounds?.top ?? 0;
  return {
    left: bounds.left - offsetX,
    top: bounds.top - offsetY,
    width: bounds.width,
    height: bounds.height,
  };
}

interface DOMRectLike {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

function rectanglesIntersect(left: DOMRectLike, right: DOMRectLike): boolean {
  return left.left <= right.right && left.right >= right.left && left.top <= right.bottom && left.bottom >= right.top;
}

function clampTreeZoom(value: number): number {
  return Math.max(TREE_ZOOM_MIN, Math.min(TREE_ZOOM_MAX, Number(value.toFixed(2))));
}

function formatTreeZoom(value: number): string {
  return Number(value.toFixed(2)).toString();
}

function expandableRelationshipRowIds(rows: RelationshipTreeRow[]): Set<string> {
  const expandableRowIds = new Set<string>();
  rows.forEach((row, index) => {
    if ((rows[index + 1]?.depth ?? -1) > row.depth) {
      expandableRowIds.add(row.id);
    }
  });
  return expandableRowIds;
}

function visibleRelationshipRows(rows: RelationshipTreeRow[], collapsedRowIds: Set<string>): RelationshipTreeRow[] {
  const visibleRows: RelationshipTreeRow[] = [];
  let collapsedDepth: number | null = null;
  for (const row of rows) {
    if (collapsedDepth !== null) {
      if (row.depth > collapsedDepth) {
        continue;
      }
      collapsedDepth = null;
    }
    visibleRows.push(row);
    if (collapsedRowIds.has(row.id)) {
      collapsedDepth = row.depth;
    }
  }
  return visibleRows;
}

export function buildRelationshipTreeRows(drawing: DrawingDocument, options: BuildRelationshipTreeOptions = {}): RelationshipTreeRow[] {
  if (options.viewMode === 'dependency') {
    return buildDependencyTreeRows(drawing, options);
  }
  const chosenGraph = chooseRelationshipGraph(drawing);
  if (!chosenGraph) {
    return [];
  }
  const dedupedGraph = dedupeRelationshipGraph(chosenGraph);
  const graph = options.viewMode === 'equipment' ? equipmentOnlyRelationshipGraph(dedupedGraph) : dedupedGraph;

  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const lineNodes = graph.nodes.filter((node) => node.kind === 'line_tag').sort(compareNodes);
  const sectionNodes = graph.nodes.filter((node) => node.kind === 'section').sort(compareNodes);
  const incomingContinuationIds = new Set(graph.edges.filter((edge) => edge.kind === 'continues_to').map((edge) => edge.targetId));
  const nestedChildIds = new Set(graph.edges.filter((edge) => TREE_PARENT_EDGE_KINDS.has(edge.kind)).map((edge) => edge.sourceId));
  const childEdgesByParentId = new Map<string, RelationshipGraphEdge[]>();
  const downstreamEdgesByLineId = new Map<string, RelationshipGraphEdge[]>();
  for (const edge of graph.edges) {
    if (TREE_PARENT_EDGE_KINDS.has(edge.kind)) {
      const edges = childEdgesByParentId.get(edge.targetId) ?? [];
      edges.push(edge);
      childEdgesByParentId.set(edge.targetId, edges);
    }
    if (edge.kind === 'continues_to') {
      const edges = downstreamEdgesByLineId.get(edge.sourceId) ?? [];
      edges.push(edge);
      downstreamEdgesByLineId.set(edge.sourceId, edges);
    }
  }
  for (const edges of childEdgesByParentId.values()) {
    edges.sort(compareEdges(graph));
  }
  for (const edges of downstreamEdgesByLineId.values()) {
    edges.sort(compareEdges(graph));
  }
  const rootsByDiscipline = new Map<string, RelationshipTreeRow>();
  const rootsByBuilding = new Map<string, RelationshipTreeRow>();
  const rootsBySystem = new Map<string, RelationshipTreeRow>();
  const rows: RelationshipTreeRow[] = [];
  const representedNodeIds = new Set<string>();
  const visitedLineIds = new Set<string>();
  const hasLineOrSectionRoots = lineNodes.length > 0 || sectionNodes.length > 0;
  const disciplines = new Set(graph.nodes.map((node) => disciplineForNode(node)).filter((discipline) => discipline !== 'Other'));
  const showDisciplineRoots = disciplines.size > 1 || (!hasLineOrSectionRoots && disciplines.size === 1);

  const pushDisciplineRoot = (discipline: string) => {
    const key = discipline || 'Other';
    const existing = rootsByDiscipline.get(key);
    if (existing) {
      return existing;
    }
    const row: RelationshipTreeRow = {
      id: `discipline:${key}`,
      depth: 0,
      tag: key,
      equipmentDescription: '',
      kind: 'discipline',
      system: '',
      relationship: 'discipline',
      parentTag: '',
      sourceFileId: '',
      page: null,
      sourcePath: '',
      sourceBounds: null,
      status: 'registered',
      confidence: null,
    };
    rootsByDiscipline.set(key, row);
    rows.push(row);
    return row;
  };

  const pushBuildingRoot = (building: string) => {
    const normalizedBuilding = canonicalBuilding(building);
    const key = normalizedBuilding;
    const existing = rootsByBuilding.get(key);
    if (existing) {
      return existing;
    }
    const row: RelationshipTreeRow = {
      id: `building:${key}`,
      depth: 0,
      tag: buildingLabel(normalizedBuilding),
      equipmentDescription: '',
      kind: 'building',
      system: '',
      relationship: 'building',
      parentTag: '',
      sourceFileId: '',
      page: null,
      sourcePath: '',
      sourceBounds: null,
      status: 'registered',
      confidence: null,
    };
    rootsByBuilding.set(key, row);
    rows.push(row);
    return row;
  };

  const pushSystemRoot = (system: string, discipline: string, building = '') => {
    const normalizedSystem = system || 'DEFAULT';
    const normalizedDiscipline = discipline || 'Other';
    const normalizedBuilding = canonicalBuilding(building);
    const key = `${normalizedBuilding ? '' : showDisciplineRoots ? normalizedDiscipline : ''}:${normalizedBuilding}:${normalizedSystem}`;
    const existing = rootsBySystem.get(key);
    if (existing) {
      return existing;
    }
    const parent = normalizedBuilding ? pushBuildingRoot(normalizedBuilding) : showDisciplineRoots ? pushDisciplineRoot(normalizedDiscipline) : null;
    const row: RelationshipTreeRow = {
      id: `system:${key}`,
      depth: parent ? parent.depth + 1 : 0,
      tag: systemLabel(normalizedSystem),
      equipmentDescription: '',
      kind: 'system',
      system: normalizedSystem,
      relationship: 'system',
      parentTag: parent?.tag ?? '',
      sourceFileId: '',
      page: null,
      sourcePath: '',
      sourceBounds: null,
      status: 'registered',
      confidence: null,
    };
    rootsBySystem.set(key, row);
    rows.push(row);
    return row;
  };

  const appendChildBranches = (parent: RelationshipGraphNode, depth: number, path: Set<string>) => {
    const childEdges = childEdgesByParentId.get(parent.id) ?? [];
    for (const childEdge of childEdges) {
      const child = nodesById.get(childEdge.sourceId);
      if (!child || path.has(child.id) || representedNodeIds.has(child.id)) {
        continue;
      }
      rows.push(nodeRow(child, depth + 1, childEdge.kind, parent.tag, childEdge));
      representedNodeIds.add(child.id);
      if (child.kind === 'line_tag') {
        visitedLineIds.add(child.id);
      }
      appendChildBranches(child, depth + 1, new Set([...path, child.id]));
    }
  };

  const appendLineBranch = (line: RelationshipGraphNode, depth: number, relationship: string, parentTag: string, edge?: RelationshipGraphEdge, path: Set<string> = new Set()) => {
    rows.push(nodeRow(line, depth, relationship, parentTag, edge));
    representedNodeIds.add(line.id);
    visitedLineIds.add(line.id);
    appendChildBranches(line, depth, new Set([...path, line.id]));

    const downstreamEdges = downstreamEdgesByLineId.get(line.id) ?? [];
    for (const downstreamEdge of downstreamEdges) {
      const linked = nodesById.get(downstreamEdge.targetId);
      if (!linked || linked.kind !== 'line_tag') {
        continue;
      }
      if (path.has(linked.id)) {
        rows.push(nodeRow(linked, depth + 1, 'continues to cycle', line.tag, downstreamEdge));
        representedNodeIds.add(linked.id);
        continue;
      }
      appendLineBranch(linked, depth + 1, 'continues to', line.tag, downstreamEdge, new Set([...path, line.id]));
    }
  };

  for (const section of sectionNodes.filter((section) => !nestedChildIds.has(section.id))) {
    const root = pushSystemRoot(section.system || 'DEFAULT', disciplineForNode(section), buildingForNode(section));
    rows.push(nodeRow(section, root.depth + 1, 'section', root.tag, undefined));
    representedNodeIds.add(section.id);
    appendChildBranches(section, root.depth + 1, new Set([section.id]));
  }

  const rootLines = lineNodes.filter((line) => !incomingContinuationIds.has(line.id) && !nestedChildIds.has(line.id));
  for (const line of rootLines) {
    const root = pushSystemRoot(line.system || 'DEFAULT', disciplineForNode(line), buildingForNode(line));
    appendLineBranch(line, root.depth + 1, 'line tag', root.tag, undefined, new Set());
  }

  for (const line of lineNodes) {
    if (visitedLineIds.has(line.id) || nestedChildIds.has(line.id)) {
      continue;
    }
    const root = pushSystemRoot(line.system || 'DEFAULT', disciplineForNode(line), buildingForNode(line));
    appendLineBranch(line, root.depth + 1, 'line tag', root.tag, undefined, new Set());
  }

  const rootEquipment = graph.nodes
    .filter((node) => node.kind === 'equipment' && !nestedChildIds.has(node.id) && !representedNodeIds.has(node.id) && (childEdgesByParentId.get(node.id)?.length ?? 0) > 0)
    .sort(compareNodes);
  for (const equipment of rootEquipment) {
    const root = pushSystemRoot(equipment.system || 'DEFAULT', disciplineForNode(equipment), buildingForNode(equipment));
    rows.push(nodeRow(equipment, root.depth + 1, 'equipment', root.tag, undefined));
    representedNodeIds.add(equipment.id);
    appendChildBranches(equipment, root.depth + 1, new Set([equipment.id]));
  }

  const orphanNodes = graph.nodes
    .filter((node) => node.kind !== 'line_tag' && !representedNodeIds.has(node.id))
    .sort(compareNodes);
  if (orphanNodes.length > 0) {
    rows.push({
      id: 'system:unresolved',
      depth: 0,
      tag: 'Unresolved / needs review',
      equipmentDescription: '',
      kind: 'review',
      system: 'DEFAULT',
      relationship: 'review',
      parentTag: '',
      sourceFileId: '',
      page: null,
      sourcePath: '',
      sourceBounds: null,
      status: 'needs_review',
      confidence: null,
    });
    for (const node of orphanNodes) {
      rows.push(nodeRow(node, 1, 'unresolved', 'Unresolved / needs review', undefined));
    }
  }

  return rows;
}

function buildDependencyTreeRows(drawing: DrawingDocument, options: BuildRelationshipTreeOptions = {}): RelationshipTreeRow[] {
  const graph = chooseDependencyGraph(drawing);
  if (!graph) {
    return [];
  }
  const activeStatuses = new Set([...(options.dependencyStatuses ?? ['confirmed', 'inferred', 'needs_review'])].map(String));
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const edgesByTargetId = new Map<string, RelationshipGraphEdge[]>();
  for (const edge of graph.edges) {
    if (!activeStatuses.has(edge.status || 'needs_review')) {
      continue;
    }
    if (!nodesById.has(edge.sourceId) || !nodesById.has(edge.targetId)) {
      continue;
    }
    const edges = edgesByTargetId.get(edge.targetId) ?? [];
    edges.push(edge);
    edgesByTargetId.set(edge.targetId, edges);
  }
  const targets = [...edgesByTargetId.keys()]
    .map((targetId) => nodesById.get(targetId))
    .filter((node): node is RelationshipGraphNode => Boolean(node))
    .sort(compareNodes);
  const rows: RelationshipTreeRow[] = [];
  for (const target of targets) {
    rows.push(dependencyTargetRow(target));
    const edges = [...(edgesByTargetId.get(target.id) ?? [])].sort(compareDependencyEdges(graph));
    for (const edge of edges) {
      const source = nodesById.get(edge.sourceId);
      if (!source) {
        continue;
      }
      rows.push(dependencySourceRow(source, target, edge));
    }
  }
  return rows;
}

function chooseRelationshipGraph(drawing: DrawingDocument): RelationshipGraphPayload | null {
  const semanticGraph = readRelationshipGraph(drawing.visualQa?.semanticRelationshipGraph);
  const sharedHierarchyGraph = readSharedHierarchyGraph(drawing.visualQa?.hierarchyViews);
  if (sharedHierarchyGraph && hasMeaningfulGraphRows(sharedHierarchyGraph.graph)) {
    if (isSharedElectricalHierarchyView(sharedHierarchyGraph) && semanticGraph && hasMeaningfulGraphRows(semanticGraph)) {
      return mergeRelationshipGraphs(semanticGraph, sharedHierarchyGraph.graph);
    }
    return sharedHierarchyGraph.graph;
  }
  const electricalGraph = readRelationshipGraph(drawing.visualQa?.electricalRelationshipGraph);
  if (electricalGraph && hasMeaningfulGraphRows(electricalGraph) && semanticGraph && hasMeaningfulGraphRows(semanticGraph)) {
    return mergeRelationshipGraphs(semanticGraph, electricalGraph);
  }
  if (electricalGraph && hasMeaningfulGraphRows(electricalGraph)) {
    return electricalGraph;
  }
  return semanticGraph;
}

function chooseDependencyGraph(drawing: DrawingDocument): RelationshipGraphPayload | null {
  const directGraph = readRelationshipGraph(drawing.visualQa?.dependencyGraph);
  if (directGraph && directGraph.edges.length > 0) {
    return directGraph;
  }
  const views = Array.isArray(drawing.visualQa?.hierarchyViews)
    ? drawing.visualQa.hierarchyViews
    : drawing.visualQa?.hierarchyViews && typeof drawing.visualQa.hierarchyViews === 'object'
      ? Object.values(drawing.visualQa.hierarchyViews as Record<string, unknown>)
      : [];
  for (const view of views) {
    if (!view || typeof view !== 'object') {
      continue;
    }
    const graph = view as Record<string, unknown>;
    if (stringValue(graph.id) !== 'commissioning_dependencies') {
      continue;
    }
    const dependencyGraph = readRelationshipGraph(graph);
    if (dependencyGraph && dependencyGraph.edges.length > 0) {
      return dependencyGraph;
    }
  }
  return null;
}

function dedupeRelationshipGraph(graph: RelationshipGraphPayload): RelationshipGraphPayload {
  const canonicalByKey = new Map<string, RelationshipGraphNode>();
  const redirectById = new Map<string, string>();
  const replacementById = new Map<string, RelationshipGraphNode>();

  for (const node of [...graph.nodes].sort(compareDuplicateNodes)) {
    const key = hierarchyDedupeKey(node);
    if (!key) {
      replacementById.set(node.id, node);
      continue;
    }
    const canonical = canonicalByKey.get(key);
    if (!canonical) {
      canonicalByKey.set(key, node);
      replacementById.set(node.id, node);
      continue;
    }
    redirectById.set(node.id, canonical.id);
    replacementById.set(canonical.id, mergeTreeNodes(replacementById.get(canonical.id) ?? canonical, node));
  }

  const nodes = graph.nodes
    .filter((node) => !redirectById.has(node.id))
    .map((node) => replacementById.get(node.id) ?? node);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges: RelationshipGraphEdge[] = [];
  const seenEdges = new Set<string>();

  for (const edge of graph.edges) {
    const sourceId = redirectById.get(edge.sourceId) ?? edge.sourceId;
    const targetId = redirectById.get(edge.targetId) ?? edge.targetId;
    if (sourceId === targetId || !nodeIds.has(sourceId) || !nodeIds.has(targetId)) {
      continue;
    }
    const redirectedEdge: RelationshipGraphEdge = {
      ...edge,
      id: edge.sourceId === sourceId && edge.targetId === targetId ? edge.id : `${edge.id}:deduped:${sourceId}:${targetId}`,
      sourceId,
      targetId,
    };
    const edgeKey = `${redirectedEdge.kind}:${redirectedEdge.sourceId}:${redirectedEdge.targetId}:${redirectedEdge.lineTag || ''}:${redirectedEdge.label || ''}`;
    if (seenEdges.has(edgeKey)) {
      continue;
    }
    seenEdges.add(edgeKey);
    edges.push(redirectedEdge);
  }

  return { nodes, edges };
}

function hierarchyDedupeKey(node: RelationshipGraphNode): string {
  const tag = canonicalHierarchyTag(node.tag);
  if (!tag || node.kind === 'discipline' || node.kind === 'system' || node.kind === 'review') {
    return '';
  }
  return `${disciplineForNode(node)}:${canonicalBuilding(buildingForNode(node))}:${tag}`;
}

function canonicalHierarchyTag(tag: string): string {
  return tag.toUpperCase().replace(/[“”]/g, '"').replace(/\s+/g, ' ').trim();
}

function buildingForNode(node: RelationshipGraphNode): string {
  const metadata = node.metadata ?? {};
  const tagProfile = objectValue(metadata.tagProfile);
  const directBuilding =
    stringValue(metadata.building)
    || stringValue(metadata.documentGuideBuilding)
    || stringValue(tagProfile.building);
  const normalizedDirectBuilding = canonicalBuilding(directBuilding);
  if (normalizedDirectBuilding) {
    return normalizedDirectBuilding;
  }
  return (
    buildingFromSheetReference(stringValue(metadata.sourceDrawingRef))
    || buildingFromSheetReference(stringValue(metadata.sourceDrawingReference))
    || buildingFromSheetReference(stringValue(metadata.drawingReference))
    || buildingFromSheetReference(node.sourcePath || stringValue(metadata.sourcePath))
    || buildingFromSheetReference(node.sourceFileId || '')
  );
}

function canonicalBuilding(building: string): string {
  const normalized = building.toUpperCase().replace(/\bBUILDING\b/g, ' ').replace(/[^A-Z0-9]+/g, ' ').trim();
  const match = normalized.match(/\b[A-Z0-9]{2,8}\b/);
  return match?.[0] ?? '';
}

function buildingLabel(building: string): string {
  return `${building} Building`;
}

function buildingFromSheetReference(value: string): string {
  if (!value) {
    return '';
  }
  const reference = value
    .split(/[\\/]/)
    .pop()
    ?.replace(/\.[A-Z0-9]+$/i, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '-') ?? '';
  const match = reference.match(/^([A-Z0-9]{2,8})-(?:ME|M|PE|PB|PL|P|E|EL|ELEC|IE|IC|FA|FP|LS|LSS|CSA|SEC|S)(?:-|(?=\d))/);
  return match ? canonicalBuilding(match[1]) : '';
}

function compareDuplicateNodes(left: RelationshipGraphNode, right: RelationshipGraphNode): number {
  return duplicateNodeRank(left) - duplicateNodeRank(right)
    || (right.confidence ?? 0) - (left.confidence ?? 0)
    || Number(Boolean(right.sourceBounds)) - Number(Boolean(left.sourceBounds))
    || (left.page ?? 99999) - (right.page ?? 99999)
    || left.id.localeCompare(right.id);
}

function duplicateNodeRank(node: RelationshipGraphNode): number {
  switch (node.kind) {
    case 'section':
      return 0;
    case 'line_tag':
      return 1;
    case 'equipment':
      return 2;
    case 'device':
      return 3;
    case 'instrument':
      return 4;
    case 'continuation':
      return 5;
    default:
      return 6;
  }
}

function mergeTreeNodes(canonical: RelationshipGraphNode, duplicate: RelationshipGraphNode): RelationshipGraphNode {
  return {
    ...canonical,
    confidence: Math.max(canonical.confidence ?? 0, duplicate.confidence ?? 0) || canonical.confidence,
    equipmentDescription: canonical.equipmentDescription || duplicate.equipmentDescription,
    sourcePath: canonical.sourcePath || duplicate.sourcePath,
    sourceBounds: canonical.sourceBounds ?? duplicate.sourceBounds ?? null,
    metadata: {
      ...(duplicate.metadata ?? {}),
      ...(canonical.metadata ?? {}),
      mergedFromNodeIds: uniqueStrings([
        ...arrayOfStrings(canonical.metadata?.mergedFromNodeIds),
        duplicate.id,
        ...arrayOfStrings(duplicate.metadata?.mergedFromNodeIds),
      ]),
      sourcePages: uniqueStrings([
        ...arrayOfStrings(canonical.metadata?.sourcePages),
        sourcePageLabel(canonical),
        sourcePageLabel(duplicate),
        ...arrayOfStrings(duplicate.metadata?.sourcePages),
      ]).filter(Boolean),
    },
  };
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : [];
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function sourcePageLabel(node: RelationshipGraphNode): string {
  return node.sourceFileId && typeof node.page === 'number' ? `${node.sourceFileId}:p${node.page}` : '';
}

function isSharedElectricalHierarchyView(view: SharedHierarchyGraph): boolean {
  return view.id === 'electrical_power' || view.discipline.toLowerCase() === 'electrical';
}

function hasElectricalRelationshipGraph(drawing: DrawingDocument): boolean {
  const electricalGraph = readRelationshipGraph(drawing.visualQa?.electricalRelationshipGraph);
  return Boolean(electricalGraph && hasMeaningfulGraphRows(electricalGraph));
}

function hasDependencyGraph(drawing: DrawingDocument): boolean {
  return Boolean(chooseDependencyGraph(drawing));
}

function defaultRelationshipViewMode(drawing: DrawingDocument): RelationshipTreeViewMode {
  if (hasElectricalRelationshipGraph(drawing)) {
    return 'equipment';
  }
  return hasDependencyGraph(drawing) ? 'dependency' : 'full';
}

function equipmentOnlyRelationshipGraph(graph: RelationshipGraphPayload): RelationshipGraphPayload {
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const visibleNodes = graph.nodes.filter(isEquipmentFlowNode);
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const parentEdgesBySourceId = new Map<string, RelationshipGraphEdge[]>();

  for (const edge of graph.edges) {
    if (!TREE_PARENT_EDGE_KINDS.has(edge.kind)) {
      continue;
    }
    const edges = parentEdgesBySourceId.get(edge.sourceId) ?? [];
    edges.push(edge);
    parentEdgesBySourceId.set(edge.sourceId, edges);
  }

  for (const edges of parentEdgesBySourceId.values()) {
    edges.sort(compareEdges(graph));
  }

  const visibleEdges: RelationshipGraphEdge[] = [];
  const seenEdges = new Set<string>();
  const addEdge = (edge: RelationshipGraphEdge) => {
    const key = `${edge.kind}:${edge.sourceId}:${edge.targetId}`;
    if (seenEdges.has(key)) {
      return;
    }
    seenEdges.add(key);
    visibleEdges.push(edge);
  };

  for (const node of visibleNodes) {
    const parent = nearestVisibleParent(node.id, visibleIds, parentEdgesBySourceId);
    if (!parent) {
      continue;
    }
    const parentNode = nodesById.get(parent.targetId);
    addEdge({
      ...parent.edge,
      id: parent.edge.sourceId === node.id && parent.edge.targetId === parent.targetId ? parent.edge.id : `equipment-flow:${node.id}:${parent.targetId}`,
      sourceId: node.id,
      targetId: parent.targetId,
      label: parentNode?.tag || parent.edge.label,
      lineTag: parentNode?.tag || parent.edge.lineTag,
    });
  }

  for (const edge of graph.edges) {
    if (edge.kind === 'continues_to' && visibleIds.has(edge.sourceId) && visibleIds.has(edge.targetId)) {
      addEdge(edge);
    }
  }

  return { nodes: visibleNodes, edges: visibleEdges };
}

function nearestVisibleParent(
  sourceId: string,
  visibleIds: Set<string>,
  parentEdgesBySourceId: Map<string, RelationshipGraphEdge[]>,
  path: Set<string> = new Set(),
): { targetId: string; edge: RelationshipGraphEdge } | null {
  if (path.has(sourceId)) {
    return null;
  }
  const nextPath = new Set(path);
  nextPath.add(sourceId);
  for (const edge of parentEdgesBySourceId.get(sourceId) ?? []) {
    if (visibleIds.has(edge.targetId)) {
      return { targetId: edge.targetId, edge };
    }
    const ancestor = nearestVisibleParent(edge.targetId, visibleIds, parentEdgesBySourceId, nextPath);
    if (ancestor) {
      return { targetId: ancestor.targetId, edge };
    }
  }
  return null;
}

function isEquipmentFlowNode(node: RelationshipGraphNode): boolean {
  if (node.metadata?.suppressInEquipmentFlow === true) {
    return false;
  }
  if (!isElectricalNode(node)) {
    return true;
  }
  if (node.kind === 'device' || node.kind === 'instrument' || node.kind === 'continuation') {
    return false;
  }
  if (node.kind === 'circuit') {
    return true;
  }
  return isUserFacingElectricalEquipmentTag(node.tag);
}

function isElectricalNode(node: RelationshipGraphNode): boolean {
  return disciplineForNode(node) === 'Electrical' || (node.system || '').toUpperCase() === 'ELEC';
}

function isUserFacingElectricalEquipmentTag(tag: string): boolean {
  const upper = normalizeElectricalTag(tag);
  if (!upper || upper.includes('BUS')) {
    return false;
  }
  if (upper === 'HV YARD SWG') {
    return true;
  }
  if (/^\d+(?:\.\d+)?\s*(?:KV|V|OHM|Ω)(?:[-/]\d+(?:\.\d+)?\s*(?:KV|V|OHM|Ω)?)*$/.test(upper)) {
    return false;
  }
  if (/^\d+(?:\.\d+)?[A-Z]?(?:AF|AT|A|KVA|KW|PF|N)?$/.test(upper)) {
    return false;
  }
  if (/^(?:AA|FA)\s+\d{3,5}KVA$/.test(upper)) {
    return false;
  }
  if (/^M\d+$/.test(upper)) {
    return false;
  }
  if (/^(?:27|32|46|47|49|50|51|52|59|81|86|87)[A-Z]{0,2}(?:-[A-Z0-9]+)?$/.test(upper)) {
    return false;
  }
  return (
    /^R[SW](?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{4,}(?:\s*&\s*[A-Z0-9-]+)?$/.test(upper)
    || /^GEN-\d[A-Z0-9-]*$/.test(upper)
    || /^R-[A-Z0-9]+(?:-[A-Z0-9]+)+(?:\s+\([A-Z0-9 ]+\))?$/.test(upper)
    || /^(?:ATS|UPS|MCC|VFD|PANEL|PNL|SWBD|SWGR|XFMR|TR|TX)-?[A-Z0-9][A-Z0-9-]*$/.test(upper)
  );
}

function normalizeElectricalTag(tag: string): string {
  return tag.toUpperCase().replace(/\s+/g, ' ').trim();
}

function titleCasePhrase(value: string): string {
  return value.toLowerCase().replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function mergeRelationshipGraphs(semanticGraph: RelationshipGraphPayload, electricalGraph: RelationshipGraphPayload): RelationshipGraphPayload {
  const electricalPageKeys = new Set(electricalGraph.nodes.map((node) => sourcePageKey(node)));
  const semanticNodeIdsToKeep = new Set(
    semanticGraph.nodes
      .filter((node) => !electricalPageKeys.has(sourcePageKey(node)))
      .map((node) => node.id),
  );
  return {
    nodes: [
      ...semanticGraph.nodes.filter((node) => semanticNodeIdsToKeep.has(node.id)),
      ...electricalGraph.nodes,
    ],
    edges: [
      ...semanticGraph.edges.filter((edge) => semanticNodeIdsToKeep.has(edge.sourceId) && semanticNodeIdsToKeep.has(edge.targetId)),
      ...electricalGraph.edges,
    ],
  };
}

function sourcePageKey(node: RelationshipGraphNode): string {
  return `${node.sourceFileId || ''}:${node.page ?? ''}`;
}

function hasMeaningfulGraphRows(graph: RelationshipGraphPayload): boolean {
  return graph.nodes.some((node) => node.kind === 'line_tag') || graph.edges.length > 0;
}

export function relationshipTreeRowsToCsv(rows: RelationshipTreeRow[]): string {
  const table = exportTableForRows(rows);
  return [
    table.columns.join(','),
    ...table.rows.map((row) => row.map(csvCell).join(',')),
  ].join('\n');
}

export function relationshipTreeRowsToJson(rows: RelationshipTreeRow[]): string {
  const table = exportTableForRows(rows);
  const records = table.rows.map((row) =>
    Object.fromEntries(table.columns.map((column, index) => [column, row[index] ?? ''])),
  );
  return JSON.stringify(records, null, 2);
}

export function relationshipTreeRowsToXlsxBlob(rows: RelationshipTreeRow[]): Blob {
  const table = exportTableForRows(rows);
  const sharedStrings: string[] = [];
  const sharedStringIndex = new Map<string, number>();
  const addSharedString = (value: string) => {
    if (!sharedStringIndex.has(value)) {
      sharedStringIndex.set(value, sharedStrings.length);
      sharedStrings.push(value);
    }
    return sharedStringIndex.get(value) ?? 0;
  };
  const xlsxRows = [table.columns, ...table.rows];
  for (const row of xlsxRows) {
    for (const value of row) {
      addSharedString(value);
    }
  }

  const sheetRows = xlsxRows
    .map((row, rowIndex) => {
      const cells = row
        .map((value, colIndex) => {
          const style = table.indentPrimaryColumn && rowIndex > 0 && colIndex === 0 ? ` s="${Math.min(Number(xlsxRows[rowIndex][1]) + 1, 13)}"` : '';
          return `<c r="${columnName(colIndex + 1)}${rowIndex + 1}"${style} t="s"><v>${addSharedString(value)}</v></c>`;
        })
        .join('');
      return `<row r="${rowIndex + 1}">${cells}</row>`;
    })
    .join('');
  const sheetXml = xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetRows}</sheetData></worksheet>`);
  const sharedXml = xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="${sharedStrings.length}" uniqueCount="${sharedStrings.length}">${sharedStrings.map((value) => `<si><t>${escapeXml(value)}</t></si>`).join('')}</sst>`);
  const workbookXml = xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${escapeXml(table.sheetName)}" sheetId="1" r:id="rId1"/></sheets></workbook>`);
  const workbookRels = xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`);
  const stylesXml = xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Arial"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="14"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>${Array.from({ length: 13 }, (_, index) => `<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment indent="${index}"/></xf>`).join('')}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`);
  const rels = xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`);
  const contentTypes = xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`);
  const zip = createZip([
    { name: '[Content_Types].xml', data: contentTypes },
    { name: '_rels/.rels', data: rels },
    { name: 'xl/workbook.xml', data: workbookXml },
    { name: 'xl/_rels/workbook.xml.rels', data: workbookRels },
    { name: 'xl/worksheets/sheet1.xml', data: sheetXml },
    { name: 'xl/sharedStrings.xml', data: sharedXml },
    { name: 'xl/styles.xml', data: stylesXml },
  ]);
  const blobBuffer = new ArrayBuffer(zip.byteLength);
  new Uint8Array(blobBuffer).set(zip);
  return new Blob([blobBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
}

function exportTableForRows(rows: RelationshipTreeRow[]): { columns: string[]; rows: string[][]; sheetName: string; indentPrimaryColumn: boolean } {
  if (isDependencyViewRows(rows)) {
    return {
      columns: DEPENDENCY_COLUMNS,
      rows: dependencyExportRows(rows),
      sheetName: 'Dependency View',
      indentPrimaryColumn: false,
    };
  }
  return {
    columns: TREE_COLUMNS,
    rows: rows.map((row) => [
      smartsheetPrimaryValue(row),
      String(row.depth),
      row.tag,
      row.equipmentDescription,
      humanizeKind(row.kind),
      row.system,
      humanizeKind(row.relationship),
      row.parentTag,
      row.sourceFileId,
      row.page === null ? '' : String(row.page),
      row.sourcePath,
      sourceBoundsLabel(row.sourceBounds),
      row.status,
      row.confidence === null ? '' : row.confidence.toFixed(3),
    ]),
    sheetName: 'Relationship Tree',
    indentPrimaryColumn: true,
  };
}

function isDependencyViewRows(rows: RelationshipTreeRow[]): boolean {
  return rows.some((row) => row.relationship === 'target_equipment' || Boolean(row.dependencyType));
}

function dependencyExportRows(rows: RelationshipTreeRow[]): string[][] {
  return rows
    .filter((row) => row.dependsOnTag || row.dependencyType)
    .map((row) => [
      row.targetTag || row.parentTag,
      row.targetEquipmentDescription || '',
      row.targetDiscipline || '',
      row.dependsOnTag || row.tag,
      row.dependsOnDescription || row.equipmentDescription,
      row.dependencyDiscipline || row.sourceDiscipline || '',
      row.dependencyType || row.relationship,
      row.status,
      row.confidence === null ? '' : row.confidence.toFixed(3),
      row.dependencyPath || '',
      row.commissioningUse || '',
      row.ruleId || '',
      row.sourceDiscipline || '',
      row.sourceFile || row.sourcePath,
      row.sourcePage === null || row.sourcePage === undefined ? '' : String(row.sourcePage),
      row.evidenceText || '',
      row.notes || '',
    ]);
}

function smartsheetPrimaryValue(row: RelationshipTreeRow): string {
  return `${'  '.repeat(Math.max(0, row.depth))}${row.tag}`;
}

function sourceBoundsLabel(bounds: Bounds | null): string {
  if (!bounds) {
    return '';
  }
  return `p${bounds.page} x${formatBoundsNumber(bounds.x)} y${formatBoundsNumber(bounds.y)} w${formatBoundsNumber(bounds.width)} h${formatBoundsNumber(bounds.height)}`;
}

function formatBoundsNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function readRelationshipGraph(value: unknown): RelationshipGraphPayload | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const graph = value as Record<string, unknown>;
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    return null;
  }
  const componentDescriptions = readGuideComponentDescriptions(graph);
  const nodes = graph.nodes.map((node) => readNode(node, componentDescriptions)).filter((node): node is RelationshipGraphNode => node !== null);
  const edges = graph.edges.map(readEdge).filter((edge): edge is RelationshipGraphEdge => edge !== null);
  return { nodes, edges };
}

function readSharedHierarchyGraph(value: unknown): SharedHierarchyGraph | null {
  const views = Array.isArray(value)
    ? value
    : value && typeof value === 'object'
      ? Object.values(value as Record<string, unknown>)
      : [];
  for (const view of views) {
    if (!view || typeof view !== 'object') {
      continue;
    }
    const graph = view as Record<string, unknown>;
    const id = stringValue(graph.id);
    if (id === 'commissioning_dependencies') {
      continue;
    }
    if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
      continue;
    }
    const componentDescriptions = readGuideComponentDescriptions(graph);
    const defaultDiscipline = stringValue(graph.discipline);
    const nodes = graph.nodes
      .map((node) => readNode(node, componentDescriptions, { discipline: defaultDiscipline }))
      .filter((node): node is RelationshipGraphNode => node !== null);
    const edges = graph.edges.map(readSharedHierarchyEdge).filter((edge): edge is RelationshipGraphEdge => edge !== null);
    if (nodes.length > 0 && edges.length > 0) {
      return { graph: { nodes, edges }, id, discipline: defaultDiscipline };
    }
  }
  return null;
}

function readNode(value: unknown, componentDescriptions: Record<string, string> = {}, defaults: { discipline?: string } = {}): RelationshipGraphNode | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const node = value as Record<string, unknown>;
  const id = stringValue(node.id);
  const tag = stringValue(node.tag);
  const kind = stringValue(node.kind);
  if (!id || !tag || !kind) {
    return null;
  }
  const metadata = node.metadata && typeof node.metadata === 'object' ? (node.metadata as Record<string, unknown>) : {};
  const sourceEvidence = firstSourceEvidence(node.sourceEvidence);
  const system = stringValue(node.system) || 'DEFAULT';
  const sourcePath = stringValue(node.sourcePath) || stringValue(metadata.sourcePath) || stringValue(sourceEvidence?.sourcePath);
  const page = numberValue(node.page) ?? numberValue(sourceEvidence?.page);
  const equipmentDescription = stringValue(node.equipmentDescription) || stringValue(node.description) || equipmentDescriptionForNode(tag, metadata, componentDescriptions);
  return {
    id,
    tag,
    kind,
    system,
    sourceFileId: stringValue(node.sourceFileId) || stringValue(sourceEvidence?.sourceFileId),
    page,
    confidence: numberValue(node.confidence),
    sourcePath,
    sourceBounds: readBounds(node.sourceBounds, page) ?? readBounds(node.bounds, page) ?? readBounds(sourceEvidence?.bounds, page),
    discipline: stringValue(node.discipline) || stringValue(metadata.discipline) || defaults.discipline || disciplineFromSourcePath(sourcePath) || disciplineFromSystem(system, tag),
    equipmentDescription,
    metadata,
  };
}

function readGuideComponentDescriptions(graph: Record<string, unknown>): Record<string, string> {
  const metrics = graph.metrics && typeof graph.metrics === 'object' ? (graph.metrics as Record<string, unknown>) : {};
  const descriptions: Record<string, string> = {};
  const documentProfile = metrics.documentProfile && typeof metrics.documentProfile === 'object' ? (metrics.documentProfile as Record<string, unknown>) : {};
  const profileCodes = documentProfile.equipmentComponentCodes && typeof documentProfile.equipmentComponentCodes === 'object'
    ? (documentProfile.equipmentComponentCodes as Record<string, unknown>)
    : {};
  const documentGuide = metrics.documentGuide && typeof metrics.documentGuide === 'object' ? (metrics.documentGuide as Record<string, unknown>) : {};
  const guideCodes = documentGuide.abbreviations && typeof documentGuide.abbreviations === 'object'
    ? (documentGuide.abbreviations as Record<string, unknown>)
    : {};

  for (const source of [profileCodes, guideCodes]) {
    for (const [code, phrase] of Object.entries(source)) {
      if (typeof phrase !== 'string' || !phrase.trim()) {
        continue;
      }
      descriptions[code.toUpperCase()] = titleCasePhrase(phrase);
    }
  }
  return descriptions;
}

function equipmentDescriptionForNode(tag: string, metadata: Record<string, unknown>, componentDescriptions: Record<string, string>): string {
  const tagProfile = metadata.tagProfile && typeof metadata.tagProfile === 'object' ? (metadata.tagProfile as Record<string, unknown>) : {};
  const directDescription = stringValue(metadata.equipmentDescription) || stringValue(metadata.documentGuideDescription) || stringValue(tagProfile.componentDescription);
  if (directDescription) {
    return titleCasePhrase(directDescription);
  }
  const explicitCode = stringValue(metadata.documentGuideComponent) || stringValue(tagProfile.componentCode);
  const componentCode = explicitCode || componentCodeFromElectricalTag(tag, componentDescriptions);
  return componentCode ? componentDescriptions[componentCode.toUpperCase()] || '' : '';
}

function componentCodeFromElectricalTag(tag: string, componentDescriptions: Record<string, string>): string {
  const upper = normalizeElectricalTag(tag);
  if (/^GEN-\d[A-Z0-9-]*$/.test(upper) && componentDescriptions.GEN) {
    return 'GEN';
  }
  for (const code of Object.keys(componentDescriptions).sort((left, right) => right.length - left.length || left.localeCompare(right))) {
    const escapedCode = escapeRegExp(code);
    if (new RegExp(`^(?:R[SW][A-Z0-9-]*?)${escapedCode}[A-Z0-9-]*$`).test(upper)) {
      return code;
    }
    if (new RegExp(`^${escapedCode}-?[A-Z0-9]`).test(upper)) {
      return code;
    }
  }
  return '';
}

function disciplineForNode(node: RelationshipGraphNode): string {
  return node.discipline || disciplineFromSourcePath(node.sourcePath || '') || disciplineFromSystem(node.system || '', node.tag) || 'Other';
}

function disciplineFromSourcePath(sourcePath: string): string {
  const lower = sourcePath.toLowerCase();
  if (lower.includes('elec')) {
    return 'Electrical';
  }
  if (lower.includes('plumb') || lower.includes('/pb') || lower.includes('-pb-')) {
    return 'Plumbing';
  }
  if (lower.includes('mech') || lower.includes('/me') || lower.includes('-me-')) {
    return 'Mechanical';
  }
  if (lower.includes('process') || lower.includes('/pe') || lower.includes('-pe-')) {
    return 'Process';
  }
  return '';
}

function disciplineFromSystem(system: string, tag: string): string {
  const upper = `${system} ${tag}`.toUpperCase();
  if (upper.includes('ELEC') || /\b(?:SWG|MDP|MCC|PANEL|XFMR|TRANSFORMER|BREAKER)\b/.test(upper)) {
    return 'Electrical';
  }
  if (/\b(?:POTCW|POTHW|SAN|ICW|POTTW|TWS|IHWH|BFP|PRV|SWF)\b/.test(upper)) {
    return 'Plumbing';
  }
  if (/\b(?:CHW|CW|HHW|HRW|CDA|SA|RA|OA|MAU|AHU|FCU|VAV|HUM|PCW|PVAC|SCHW|SHRW)\b/.test(upper)) {
    return 'Mechanical';
  }
  if (/\b(?:CAL|CAU|SUL|AW|FW|UHP|LPN|LPO)\b/.test(upper)) {
    return 'Process';
  }
  return '';
}

function readEdge(value: unknown): RelationshipGraphEdge | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const edge = value as Record<string, unknown>;
  const kind = stringValue(edge.kind);
  const sourceId = stringValue(edge.sourceId);
  const targetId = stringValue(edge.targetId);
  if (!kind || !sourceId || !targetId) {
    return null;
  }
  return {
    id: stringValue(edge.id) || `${kind}:${sourceId}:${targetId}`,
    kind,
    sourceId,
    targetId,
    sourceTag: stringValue(edge.sourceTag),
    targetTag: stringValue(edge.targetTag),
    label: stringValue(edge.label),
    lineTag: stringValue(edge.lineTag),
    system: stringValue(edge.system),
    status: stringValue(edge.status),
    confidence: numberValue(edge.confidence),
    ruleId: stringValue(edge.ruleId),
    sourceEvidenceIds: arrayOfStrings(edge.sourceEvidenceIds),
    metadata: edge.metadata && typeof edge.metadata === 'object' ? (edge.metadata as Record<string, unknown>) : {},
  };
}

function readSharedHierarchyEdge(value: unknown): RelationshipGraphEdge | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const edge = value as Record<string, unknown>;
  const kind = stringValue(edge.kind);
  if (!kind) {
    return null;
  }

  const explicitParentId = stringValue(edge.parentId);
  const explicitChildId = stringValue(edge.childId);
  if (explicitParentId && explicitChildId) {
    return sharedHierarchyEdge(edge, kind, explicitChildId, explicitParentId);
  }

  const source = stringValue(edge.source);
  const target = stringValue(edge.target);
  if (source && target) {
    return sharedHierarchyEdge(edge, kind, target, source);
  }

  const sourceId = stringValue(edge.sourceId);
  const targetId = stringValue(edge.targetId);
  if (sourceId && targetId) {
    return sharedHierarchyEdge(edge, kind, sourceId, targetId);
  }

  return null;
}

function sharedHierarchyEdge(edge: Record<string, unknown>, kind: string, sourceId: string, targetId: string): RelationshipGraphEdge {
  return {
    id: stringValue(edge.id) || `${kind}:${sourceId}:${targetId}`,
    kind,
    sourceId,
    targetId,
    sourceTag: stringValue(edge.sourceTag),
    targetTag: stringValue(edge.targetTag),
    label: stringValue(edge.label),
    lineTag: stringValue(edge.lineTag),
    system: stringValue(edge.system),
    status: stringValue(edge.status),
    confidence: numberValue(edge.confidence),
    ruleId: stringValue(edge.ruleId),
    sourceEvidenceIds: arrayOfStrings(edge.sourceEvidenceIds),
    metadata: edge.metadata && typeof edge.metadata === 'object' ? (edge.metadata as Record<string, unknown>) : {},
  };
}

function firstSourceEvidence(value: unknown): Record<string, unknown> | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const evidence = value.find((candidate) => candidate && typeof candidate === 'object');
  return evidence ? (evidence as Record<string, unknown>) : null;
}

function nodeRow(
  node: RelationshipGraphNode,
  depth: number,
  relationship: string,
  parentTag: string,
  edge: RelationshipGraphEdge | undefined,
): RelationshipTreeRow {
  const relationshipKey = edge?.id || `${relationship}:${parentTag}`;
  return {
    id: `node:${node.id}:${relationshipKey}`,
    depth,
    tag: node.tag,
    equipmentDescription: node.equipmentDescription || '',
    kind: node.kind,
    system: edge?.system || node.system || 'DEFAULT',
    relationship,
    parentTag,
    sourceFileId: node.sourceFileId || '',
    page: typeof node.page === 'number' ? node.page : null,
    sourcePath: node.sourcePath || '',
    sourceBounds: node.sourceBounds ?? null,
    status: edge?.status || 'registered',
    confidence: edge?.confidence ?? node.confidence ?? null,
  };
}

function dependencyTargetRow(target: RelationshipGraphNode): RelationshipTreeRow {
  return {
    id: `dependency-target:${target.id}`,
    depth: 0,
    tag: target.tag,
    equipmentDescription: target.equipmentDescription || '',
    kind: target.kind,
    system: target.system || 'DEFAULT',
    relationship: 'target_equipment',
    parentTag: '',
    sourceFileId: target.sourceFileId || '',
    page: typeof target.page === 'number' ? target.page : null,
    sourcePath: target.sourcePath || '',
    sourceBounds: target.sourceBounds ?? null,
    status: 'registered',
    confidence: target.confidence ?? null,
    targetTag: target.tag,
    targetEquipmentDescription: target.equipmentDescription || '',
    targetDiscipline: target.discipline || '',
  };
}

function dependencySourceRow(source: RelationshipGraphNode, target: RelationshipGraphNode, edge: RelationshipGraphEdge): RelationshipTreeRow {
  const metadata = edge.metadata ?? {};
  const sourcePage = numberValue(metadata.sourcePage) ?? source.page ?? target.page ?? null;
  const sourceFile = stringValue(metadata.sourcePath) || source.sourcePath || target.sourcePath || source.sourceFileId || '';
  return {
    id: `dependency-edge:${edge.id}`,
    depth: 1,
    tag: source.tag,
    equipmentDescription: source.equipmentDescription || '',
    kind: source.kind,
    system: edge.system || source.system || target.system || 'DEFAULT',
    relationship: edge.kind,
    parentTag: target.tag,
    sourceFileId: source.sourceFileId || '',
    page: typeof source.page === 'number' ? source.page : null,
    sourcePath: source.sourcePath || '',
    sourceBounds: source.sourceBounds ?? null,
    status: edge.status || 'needs_review',
    confidence: edge.confidence ?? source.confidence ?? null,
    targetTag: edge.targetTag || target.tag,
    targetEquipmentDescription: target.equipmentDescription || '',
    targetDiscipline: stringValue(metadata.targetDiscipline) || target.discipline || '',
    dependsOnTag: edge.sourceTag || source.tag,
    dependsOnDescription: source.equipmentDescription || '',
    dependencyDiscipline: source.discipline || stringValue(metadata.sourceDiscipline) || '',
    dependencyType: edge.kind,
    dependencyPath: stringValue(metadata.dependencyPath),
    commissioningUse: stringValue(metadata.commissioningUse),
    ruleId: edge.ruleId || '',
    sourceDiscipline: stringValue(metadata.sourceDiscipline) || source.discipline || '',
    sourceFile,
    sourcePage,
    evidenceText: stringValue(metadata.evidenceText) || (edge.sourceEvidenceIds ?? []).join(', '),
    notes: stringValue(metadata.notes),
  };
}

function compareNodes(left: RelationshipGraphNode, right: RelationshipGraphNode): number {
  return (left.system || '').localeCompare(right.system || '') || (left.sourceFileId || '').localeCompare(right.sourceFileId || '') || (left.page ?? 0) - (right.page ?? 0) || compareNodePositions(left, right) || left.tag.localeCompare(right.tag);
}

function compareEdges(graph: RelationshipGraphPayload) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  return (left: RelationshipGraphEdge, right: RelationshipGraphEdge): number => {
    const leftNode = nodeById.get(left.sourceId) ?? nodeById.get(left.targetId);
    const rightNode = nodeById.get(right.sourceId) ?? nodeById.get(right.targetId);
    return relationshipSortRank(left.kind) - relationshipSortRank(right.kind) || compareNodePositions(leftNode, rightNode) || (leftNode?.tag || '').localeCompare(rightNode?.tag || '') || left.kind.localeCompare(right.kind);
  };
}

function compareDependencyEdges(graph: RelationshipGraphPayload) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  return (left: RelationshipGraphEdge, right: RelationshipGraphEdge): number => {
    const leftNode = nodeById.get(left.sourceId);
    const rightNode = nodeById.get(right.sourceId);
    return dependencySortRank(left.kind) - dependencySortRank(right.kind)
      || (leftNode?.tag || left.sourceTag || '').localeCompare(rightNode?.tag || right.sourceTag || '')
      || left.id.localeCompare(right.id);
  };
}

function compareNodePositions(left?: RelationshipGraphNode, right?: RelationshipGraphNode): number {
  const leftBounds = left?.sourceBounds;
  const rightBounds = right?.sourceBounds;
  if (!leftBounds || !rightBounds) {
    return 0;
  }
  const yDelta = leftBounds.y - rightBounds.y;
  if (Math.abs(yDelta) > 18) {
    return yDelta;
  }
  return leftBounds.x - rightBounds.x;
}

function relationshipSortRank(kind: string): number {
  switch (kind) {
    case 'represents_instance':
      return 10;
    case 'control_panel_for':
    case 'feeds_panel':
    case 'panel_schedule_feeds':
      return 20;
    case 'control_point_on_panel':
    case 'panel_circuit':
      return 30;
    case 'equipment_component':
    case 'device_on_equipment':
      return 40;
    case 'instrument_on_equipment':
    case 'instrument_on_line':
    case 'device_on_line':
    case 'attached_to_line':
      return 50;
    case 'continuation_on_line':
      return 60;
    default:
      return 90;
  }
}

function dependencySortRank(kind: string): number {
  switch (kind) {
    case 'requires_drive':
      return 10;
    case 'requires_power':
      return 20;
    case 'requires_upstream_distribution':
      return 30;
    case 'requires_feeder':
      return 40;
    case 'requires_transformer':
      return 50;
    case 'requires_backup_power':
      return 60;
    case 'requires_driven_equipment':
      return 70;
    case 'requires_motor':
      return 80;
    case 'requires_control_panel':
      return 90;
    case 'requires_instrument':
      return 100;
    default:
      return 120;
  }
}

function downloadRelationshipCsv(rows: RelationshipTreeRow[], filename: string) {
  downloadBlob(new Blob([relationshipTreeRowsToCsv(rows)], { type: 'text/csv;charset=utf-8' }), filename);
}

function downloadRelationshipXlsx(rows: RelationshipTreeRow[], filename: string) {
  downloadBlob(relationshipTreeRowsToXlsxBlob(rows), filename);
}

function downloadRelationshipJson(rows: RelationshipTreeRow[], filename: string) {
  downloadBlob(new Blob([relationshipTreeRowsToJson(rows)], { type: 'application/json;charset=utf-8' }), filename);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function createZip(files: Array<{ name: string; data: Uint8Array }>): Uint8Array {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;
  for (const file of files) {
    const name = utf8(file.name);
    const crc = crc32(file.data);
    const local = concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(file.data.length),
      u32(file.data.length),
      u16(name.length),
      u16(0),
      name,
      file.data,
    ]);
    localParts.push(local);
    centralParts.push(
      concat([
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(crc),
        u32(file.data.length),
        u32(file.data.length),
        u16(name.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(offset),
        name,
      ]),
    );
    offset += local.length;
  }
  const central = concat(centralParts);
  const end = concat([u32(0x06054b50), u16(0), u16(0), u16(files.length), u16(files.length), u32(central.length), u32(offset), u16(0)]);
  return concat([...localParts, central, end]);
}

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let index = 0; index < 8; index += 1) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let cursor = 0;
  for (const part of parts) {
    out.set(part, cursor);
    cursor += part.length;
  }
  return out;
}

function u16(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}

function u32(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff]);
}

function xml(value: string): Uint8Array {
  return utf8(value.trim());
}

function utf8(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function escapeXml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function columnName(index: number): string {
  let value = '';
  let current = index;
  while (current > 0) {
    current -= 1;
    value = String.fromCharCode(65 + (current % 26)) + value;
    current = Math.floor(current / 26);
  }
  return value;
}

function csvCell(value: string | number): string {
  const text = String(value);
  return /[",\n]|^\s|\s$/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function systemLabel(system: string): string {
  return system === 'DEFAULT' ? 'Unclassified System' : `${system} System`;
}

function humanizeKind(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function humanizeStatus(value: string): string {
  return value === 'needs_review' ? 'Needs review' : humanizeKind(value || 'registered');
}

function statusClass(value: string): string {
  return (value || 'registered').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
}

function sanitizeFileStem(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'pid-relationship-tree';
}

function treeRowTitle(row: RelationshipTreeRow): string {
  const parts = [
    row.tag,
    row.equipmentDescription,
    humanizeKind(row.kind),
    humanizeKind(row.relationship),
    row.system ? `${row.system} system` : '',
    row.status,
    row.confidence === null ? '' : `${Math.round(row.confidence * 100)}% confidence`,
    row.sourceFileId ? `source ${row.sourceFileId}` : '',
    row.page === null ? '' : `page ${row.page}`,
  ].filter(Boolean);
  return parts.join(' | ');
}

function confidenceLabel(confidence: number | null): string {
  return confidence === null ? '—' : `${Math.round(confidenceScore(confidence) * 100)}%`;
}

function confidenceLevel(confidence: number | null): string {
  if (confidence === null) {
    return 'none';
  }
  if (confidence >= 0.82) {
    return 'high';
  }
  if (confidence >= 0.68) {
    return 'medium';
  }
  return 'low';
}

function confidenceScore(confidence: number | null): number {
  if (confidence === null || !Number.isFinite(confidence)) {
    return 0;
  }
  return Math.max(0, Math.min(1, confidence));
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function readBounds(value: unknown, page: number | undefined): Bounds | null {
  if (!value || typeof value !== 'object' || typeof page !== 'number') {
    return null;
  }
  const bounds = value as Record<string, unknown>;
  const x = numberValue(bounds.x);
  const y = numberValue(bounds.y);
  const width = numberValue(bounds.width);
  const height = numberValue(bounds.height);
  if (x === undefined || y === undefined || width === undefined || height === undefined) {
    return null;
  }
  return { page, x, y, width, height };
}
