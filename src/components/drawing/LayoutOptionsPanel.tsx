import { Check, Gauge } from 'lucide-react';
import { useState } from 'react';
import type { CSSProperties } from 'react';
import type { DrawingDocument, DrawingMetricValue, LayoutOption } from '../../types';
import { objectLayerIds } from './DrawingCanvas';
import { PID_SYMBOL_CATEGORIES, PID_SYMBOL_MASTER_SHEET_PATH, PidSymbolShape } from './PidSymbolLibrary';
import { buildRelationshipTreeRows, PidRelationshipTree } from './PidRelationshipTree';

interface LayoutOptionsPanelProps {
  options: LayoutOption[];
  activeOptionId?: string | null;
  onChooseOption: (option: LayoutOption) => void;
  drawing?: DrawingDocument;
  hiddenLayerIds?: string[];
  showPrintBoundary?: boolean;
  showMinimap?: boolean;
  onToggleLayer?: (layerId: string) => void;
  onTogglePrintBoundary?: () => void;
  onToggleMinimap?: () => void;
  onSelectObject?: (id: string | null) => void;
  onAddSymbol?: (symbolType: string) => void;
  className?: string;
}

export function LayoutOptionsPanel({
  options,
  activeOptionId,
  onChooseOption,
  drawing,
  hiddenLayerIds = [],
  showPrintBoundary = false,
  showMinimap = false,
  onToggleLayer,
  onTogglePrintBoundary,
  onToggleMinimap,
  onSelectObject,
  onAddSymbol,
  className,
}: LayoutOptionsPanelProps) {
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('layers');
  const hidden = new Set(hiddenLayerIds);
  const layerRows = drawing ? layerInventory(drawing) : [];
  const reviewRows = drawing ? reviewQueue(drawing) : [];
  const legendRows = drawing ? legendInventory(drawing) : [];
  const treeRows = drawing ? buildRelationshipTreeRows(drawing) : [];
  const symbolCount = PID_SYMBOL_CATEGORIES.reduce((total, category) => total + category.types.length, 0);

  return (
    <aside className={`drawing-options-panel${className ? ` ${className}` : ''}`} aria-label="Drawing controls">
      <section className="drawing-control-section drawing-control-section--layouts">
        <div className="drawing-panel-heading">
          <h2>Layouts</h2>
          <span>{options.length}</span>
        </div>
        {options.length === 0 ? (
          <p className="drawing-panel-empty">No generated layout options.</p>
        ) : (
          <div className="drawing-layout-options">
            {options.map((option) => {
              const active = option.id === activeOptionId;
              return (
                <button
                  key={option.id}
                  type="button"
                  className={`drawing-layout-option${active ? ' drawing-layout-option--active' : ''}`}
                  onClick={() => onChooseOption(option)}
                  aria-pressed={active}
                >
                  <span className="drawing-layout-option__topline">
                    <strong>{option.name}</strong>
                    <span className="drawing-layout-option__score">
                      {active ? <Check size={13} /> : <Gauge size={13} />}
                      {formatScore(option.score)}
                    </span>
                  </span>
                  {option.description ? <span className="drawing-layout-option__description">{option.description}</span> : null}
                  <span className="drawing-layout-option__metrics">
                    {layoutMetricEntries(option.metrics).map(([key, value]) => (
                      <span key={key}>
                        <small>{humanizeMetricKey(key)}</small>
                        <b>{formatMetricValue(value)}</b>
                      </span>
                    ))}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="drawing-control-section drawing-workbench-section">
        <div className="drawing-workbench-tabs" role="tablist" aria-label="Drawing workbench">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'layers'}
            className={activeTab === 'layers' ? 'drawing-workbench-tab drawing-workbench-tab--active' : 'drawing-workbench-tab'}
            onClick={() => setActiveTab('layers')}
          >
            <span>Layers</span>
            <b>{layerRows.length}</b>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'reviews'}
            className={activeTab === 'reviews' ? 'drawing-workbench-tab drawing-workbench-tab--active' : 'drawing-workbench-tab'}
            onClick={() => setActiveTab('reviews')}
          >
            <span>Reviews</span>
            <b>{reviewRows.length}</b>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'legend'}
            className={activeTab === 'legend' ? 'drawing-workbench-tab drawing-workbench-tab--active' : 'drawing-workbench-tab'}
            onClick={() => setActiveTab('legend')}
          >
            <span>Legend</span>
            <b>{legendRows.length}</b>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'tree'}
            className={activeTab === 'tree' ? 'drawing-workbench-tab drawing-workbench-tab--active' : 'drawing-workbench-tab'}
            onClick={() => setActiveTab('tree')}
          >
            <span>Tree</span>
            <b>{treeRows.length}</b>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'symbols'}
            className={activeTab === 'symbols' ? 'drawing-workbench-tab drawing-workbench-tab--active' : 'drawing-workbench-tab'}
            onClick={() => setActiveTab('symbols')}
          >
            <span>Symbols</span>
            <b>{symbolCount}</b>
          </button>
        </div>

        <div className="drawing-workbench-panel" role="tabpanel" aria-label={`${activeTabLabel(activeTab)} panel`}>
          {activeTab === 'layers' ? (
            <div className="drawing-layer-list">
              {layerRows.map((layer) => {
                const visible = !hidden.has(layer.id);
                return (
                  <button
                    key={layer.id}
                    type="button"
                    className={visible ? 'drawing-layer-row' : 'drawing-layer-row drawing-layer-row--hidden'}
                    title={`${visible ? 'Hide' : 'Show'} ${layer.label.toLowerCase()}`}
                    aria-pressed={visible}
                    onClick={() => onToggleLayer?.(layer.id)}
                  >
                    <span className="drawing-layer-row__switch" aria-hidden="true" />
                    <span>{layer.label}</span>
                    <b>{layer.count}</b>
                  </button>
                );
              })}
              <button
                type="button"
                className={showPrintBoundary ? 'drawing-layer-row' : 'drawing-layer-row drawing-layer-row--hidden'}
                title={showPrintBoundary ? 'Hide print boundary' : 'Show print boundary'}
                aria-pressed={showPrintBoundary}
                onClick={onTogglePrintBoundary}
              >
                <span className="drawing-layer-row__switch" aria-hidden="true" />
                <span>Print boundary</span>
                <b>{showPrintBoundary ? 'on' : 'off'}</b>
              </button>
              <button
                type="button"
                className={showMinimap ? 'drawing-layer-row' : 'drawing-layer-row drawing-layer-row--hidden'}
                title={showMinimap ? 'Hide minimap' : 'Show minimap'}
                aria-pressed={showMinimap}
                onClick={onToggleMinimap}
              >
                <span className="drawing-layer-row__switch" aria-hidden="true" />
                <span>Minimap</span>
                <b>{showMinimap ? 'on' : 'off'}</b>
              </button>
            </div>
          ) : null}

          {activeTab === 'reviews' ? (
            reviewRows.length === 0 ? (
              <p className="drawing-panel-empty">No continuation objects marked for review.</p>
            ) : (
              <div className="drawing-review-queue">
                {reviewRows.slice(0, 14).map((item) => (
                  <button key={item.id} type="button" className="drawing-review-row" onClick={() => onSelectObject?.(item.objectId)}>
                    <span>{item.label}</span>
                    <b>{item.sheetRef || 'needs review'}</b>
                  </button>
                ))}
              </div>
            )
          ) : null}

          {activeTab === 'legend' ? (
            <div className="drawing-legend-table">
              {legendRows.map((row) => (
                <div key={row.id} className="drawing-legend-row">
                  <span className="drawing-legend-row__sample" style={{ '--legend-color': row.color } as CSSProperties} />
                  <span>{row.label}</span>
                  <b>{row.kind}</b>
                </div>
              ))}
            </div>
          ) : null}

          {activeTab === 'tree' && drawing ? <PidRelationshipTree drawing={drawing} /> : null}

          {activeTab === 'symbols' ? (
            <div className="drawing-symbol-library">
              <div className="drawing-symbol-library__header">
                <span>Recreation vector pack</span>
                <a href={PID_SYMBOL_MASTER_SHEET_PATH} target="_blank" rel="noreferrer">
                  Master sheet
                </a>
              </div>
              {PID_SYMBOL_CATEGORIES.map((category) => (
                <section className="drawing-symbol-library__section" key={category.id} aria-label={`${category.label} symbols`}>
                  <div className="drawing-symbol-library__section-title">
                    <span>{category.label}</span>
                    <b>{category.types.length}</b>
                  </div>
                  <div className="drawing-symbol-library__grid">
                    {category.types.map((type) => {
                      const label = humanizeSymbolType(type);
                      return (
                        <button
                          key={type}
                          type="button"
                          className="drawing-symbol-library__row"
                          title={`Place ${label}`}
                          onClick={() => onAddSymbol?.(type)}
                        >
                          <svg viewBox="0 0 54 38" aria-hidden="true">
                            <PidSymbolShape
                              bounds={{ x: 5, y: 4, width: 44, height: 30 }}
                              stroke="#111827"
                              fill="#ffffff"
                              strokeWidth={1.25}
                              opacity={1}
                              symbolType={type}
                            />
                          </svg>
                          <span>{label}</span>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          ) : null}
        </div>
      </section>
    </aside>
  );
}

type WorkbenchTab = 'layers' | 'reviews' | 'legend' | 'tree' | 'symbols';

function activeTabLabel(tab: WorkbenchTab): string {
  switch (tab) {
    case 'layers':
      return 'Layers';
    case 'reviews':
      return 'Reviews';
    case 'legend':
      return 'Legend';
    case 'tree':
      return 'Tree';
    case 'symbols':
      return 'Symbols';
  }
}

const LAYERS = [
  { id: 'source', label: 'Source map' },
  { id: 'semantic', label: 'Semantic overlay' },
  { id: 'zones', label: 'Areas / regions' },
  { id: 'routing', label: 'Routing polish' },
  { id: 'continuations', label: 'Continuations' },
  { id: 'lines', label: 'Lines' },
  { id: 'symbols', label: 'Symbols' },
  { id: 'labels', label: 'Labels' },
  { id: 'coverage', label: 'Coverage index' },
] as const;

function layerInventory(drawing: DrawingDocument): Array<{ id: string; label: string; count: number }> {
  const counts = new Map<string, number>();
  for (const object of drawing.objects) {
    for (const layer of objectLayerIds(object)) {
      counts.set(layer, (counts.get(layer) ?? 0) + 1);
    }
  }
  return LAYERS.map((layer) => ({ ...layer, count: counts.get(layer.id) ?? 0 }));
}

function reviewQueue(drawing: DrawingDocument): Array<{ id: string; objectId: string; label: string; sheetRef: string }> {
  const seen = new Set<string>();
  const rows = [];
  for (const object of drawing.objects) {
    const metadata = object.metadata ?? {};
    const candidateId = typeof metadata.sourceCandidateId === 'string' ? metadata.sourceCandidateId : '';
    if (!candidateId || seen.has(candidateId)) {
      continue;
    }
    seen.add(candidateId);
    rows.push({
      id: candidateId,
      objectId: object.id,
      label: object.label || String(metadata.lineTag ?? candidateId),
      sheetRef: typeof metadata.sheetRef === 'string' ? metadata.sheetRef : '',
    });

    if (
      object.kind === 'pipe' || object.kind === 'connector'
    ) {
      const danglingEnds = ['start', 'end'].filter((endpoint) => metadata[`${endpoint}ConnectionType`] === 'dangling');
      if (danglingEnds.length > 0) {
        const reviewId = `${object.id}:dangling:${danglingEnds.join('-')}`;
        if (!seen.has(reviewId)) {
          seen.add(reviewId);
          rows.push({
            id: reviewId,
            objectId: object.id,
            label: object.label || object.id,
            sheetRef: `Dangling endpoint${danglingEnds.length > 1 ? 's' : ''}`,
          });
        }
      }
    }
  }
  return rows;
}

function legendInventory(drawing: DrawingDocument): Array<{ id: string; label: string; color: string; kind: string }> {
  const systems = new Map<string, string>();
  for (const object of drawing.objects) {
    const system = typeof object.metadata?.system === 'string' ? object.metadata.system : '';
    if (system && !systems.has(system)) {
      systems.set(system, object.style.stroke || '#334155');
    }
  }
  const rows = Array.from(systems, ([system, color]) => ({
    id: `system-${system}`,
    label: system,
    color,
    kind: 'system',
  }));
  rows.push(
    { id: 'legend-offpage', label: 'Off-page continuation', color: '#111827', kind: 'symbol' },
    { id: 'legend-review', label: 'Needs review / source-derived', color: '#64748b', kind: 'dash' },
    { id: 'legend-area', label: 'Area / scope boundary', color: '#dc2626', kind: 'region' },
  );
  return rows;
}

function layoutMetricEntries(metrics: Record<string, DrawingMetricValue>): Array<[string, DrawingMetricValue]> {
  const priority = [
    'sourceFaithfulness',
    'detectedGroups',
    'matchedContinuations',
    'editableObjects',
    'systemPages',
    'crossings',
    'labelOverlaps',
    'connectivityConnectedEndpoints',
    'connectivityDanglingEndpoints',
    'sourceGenerated',
  ];
  const entries = Object.entries(metrics);
  const byKey = new Map(entries);
  const picked: Array<[string, DrawingMetricValue]> = [];
  for (const key of priority) {
    if (byKey.has(key)) {
      picked.push([key, byKey.get(key) as DrawingMetricValue]);
    }
    if (picked.length >= 4) {
      return picked;
    }
  }
  for (const entry of entries) {
    if (!priority.includes(entry[0])) {
      picked.push(entry);
    }
    if (picked.length >= 4) {
      return picked;
    }
  }
  return picked;
}

function formatScore(score: number): string {
  if (!Number.isFinite(score)) {
    return 'n/a';
  }
  return score <= 1 ? `${Math.round(score * 100)}%` : score.toFixed(1);
}

function formatMetricValue(value: DrawingMetricValue): string {
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return 'n/a';
    }
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === 'boolean') {
    return value ? 'yes' : 'no';
  }
  if (value === null) {
    return 'n/a';
  }
  return String(value);
}

function humanizeMetricKey(key: string): string {
  return key.replace(/[_-]/g, ' ');
}

function humanizeSymbolType(type: string): string {
  return type
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
