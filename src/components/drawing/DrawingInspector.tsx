import { useId } from 'react';
import { AlignCenter, AlignLeft, AlignRight, Bold, CornerDownRight, FileSearch, Italic, Lock, Trash2, Unlock } from 'lucide-react';
import type { DrawingBounds, DrawingObject, DrawingStyle, PageEvidence } from '../../types';

interface DrawingInspectorProps {
  selectedObject: DrawingObject | null;
  onUpdateLabel: (id: string, label: string) => void;
  onUpdateStyle: (id: string, style: Partial<DrawingStyle>) => void;
  onUpdateMetadata?: (id: string, metadata: Record<string, unknown>) => void;
  onUpdateBounds?: (id: string, bounds: DrawingBounds) => void;
  onAddConnectorBend?: (id: string) => void;
  onDeleteObject?: (id: string) => void;
  sourcePages?: PageEvidence[];
  projectId?: string;
  apiBaseUrl?: string | null;
  onOpenSourcePage?: (page: PageEvidence) => void;
  className?: string;
}

export function DrawingInspector({
  selectedObject,
  onUpdateLabel,
  onUpdateStyle,
  onUpdateMetadata,
  onUpdateBounds,
  onAddConnectorBend,
  onDeleteObject,
  sourcePages = [],
  projectId = '',
  apiBaseUrl,
  onOpenSourcePage,
  className,
}: DrawingInspectorProps) {
  if (!selectedObject) {
    return (
      <aside className={`drawing-inspector${className ? ` ${className}` : ''}`} aria-label="Drawing inspector">
        <div className="drawing-panel-heading">
          <h2>Inspector</h2>
        </div>
        <p className="drawing-panel-empty">Select an object to inspect drawing properties.</p>
      </aside>
    );
  }

  const locked = selectedObject.locked === true;
  const style = selectedObject.style;
  const isConnector = selectedObject.kind === 'pipe' || selectedObject.kind === 'connector';
  const isLabel = selectedObject.kind === 'label';
  const canResize = selectedObject.kind === 'symbol' || selectedObject.kind === 'region' || selectedObject.kind === 'label';
  const metadata = selectedObject.metadata ?? {};
  const linkedSourcePages = sourcePagesForObject(selectedObject, sourcePages);

  return (
    <aside className={`drawing-inspector${className ? ` ${className}` : ''}`} aria-label="Drawing inspector">
      <div className="drawing-panel-heading">
        <h2>Inspector</h2>
        <span className={locked ? 'drawing-lock-state drawing-lock-state--locked' : 'drawing-lock-state'}>
          {locked ? <Lock size={13} /> : <Unlock size={13} />}
          {locked ? 'Locked' : 'Editable'}
        </span>
      </div>

      <dl className="drawing-inspector__meta">
        <div>
          <dt>Kind</dt>
          <dd>{selectedObject.kind.replace(/_/g, ' ')}</dd>
        </div>
        <div>
          <dt>ID</dt>
          <dd title={selectedObject.id}>{selectedObject.id}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{selectedObject.sourceEvidenceIds.length}</dd>
        </div>
      </dl>

      <div className="drawing-inspector__section">
        <h3>Label</h3>
        <label className="drawing-field">
          <span>Text</span>
          <input
            value={selectedObject.label}
            disabled={locked}
            onChange={(event) => onUpdateLabel(selectedObject.id, event.target.value)}
          />
        </label>
      </div>

      <div className="drawing-inspector__section">
        <h3>Style</h3>
        <ColorField
          label="Stroke"
          value={style.stroke}
          disabled={locked}
          onChange={(stroke) => onUpdateStyle(selectedObject.id, { stroke })}
        />
        <ColorField
          label="Fill"
          value={style.fill}
          disabled={locked}
          onChange={(fill) => onUpdateStyle(selectedObject.id, { fill })}
        />
        <label className="drawing-field drawing-field--split">
          <span>Stroke width</span>
          <input
            type="number"
            min={0.25}
            max={24}
            step={0.25}
            value={style.strokeWidth}
            disabled={locked}
            onChange={(event) => onUpdateNumber(selectedObject.id, 'strokeWidth', event.target.value, onUpdateStyle)}
          />
        </label>
        <label className="drawing-field">
          <span>Opacity</span>
          <span className="drawing-range-field">
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={style.opacity}
              disabled={locked}
              onChange={(event) => onUpdateNumber(selectedObject.id, 'opacity', event.target.value, onUpdateStyle)}
            />
            <b>{Math.round(style.opacity * 100)}%</b>
          </span>
        </label>
        {isConnector ? (
          <label className="drawing-field">
            <span>Line pattern</span>
            <select
              value={dashPreset(style.dash)}
              disabled={locked}
              onChange={(event) => onUpdateStyle(selectedObject.id, { dash: dashForPreset(event.target.value) })}
            >
              <option value="solid">Solid</option>
              <option value="dashed">Dashed</option>
              <option value="dotted">Dotted</option>
              <option value="dash-dot">Dash dot</option>
            </select>
          </label>
        ) : null}
      </div>

      {canResize ? (
        <div className="drawing-inspector__section">
          <h3>Geometry</h3>
          <div className="drawing-geometry-grid">
            <NumberField
              label="X"
              value={Math.round(selectedObject.bounds.x)}
              disabled={locked}
              onChange={(value) => updateBoundsNumber(selectedObject, 'x', value, onUpdateBounds)}
            />
            <NumberField
              label="Y"
              value={Math.round(selectedObject.bounds.y)}
              disabled={locked}
              onChange={(value) => updateBoundsNumber(selectedObject, 'y', value, onUpdateBounds)}
            />
            <NumberField
              label="W"
              value={Math.round(selectedObject.bounds.width)}
              disabled={locked}
              min={8}
              onChange={(value) => updateBoundsNumber(selectedObject, 'width', value, onUpdateBounds)}
            />
            <NumberField
              label="H"
              value={Math.round(selectedObject.bounds.height)}
              disabled={locked}
              min={8}
              onChange={(value) => updateBoundsNumber(selectedObject, 'height', value, onUpdateBounds)}
            />
          </div>
        </div>
      ) : null}

      {isConnector ? (
        <div className="drawing-inspector__section">
          <h3>Line edits</h3>
          <div className="drawing-inspector__button-row">
            <button
              className="drawing-inspector__action-button"
              type="button"
              disabled={locked}
              onClick={() => onAddConnectorBend?.(selectedObject.id)}
            >
              <CornerDownRight size={15} />
              <span>Add bend</span>
            </button>
            <button
              className="drawing-inspector__action-button drawing-inspector__action-button--danger"
              type="button"
              disabled={locked}
              onClick={() => onDeleteObject?.(selectedObject.id)}
            >
              <Trash2 size={15} />
              <span>Delete</span>
            </button>
          </div>
        </div>
      ) : null}

      {isLabel ? (
        <div className="drawing-inspector__section">
          <h3>Typography</h3>
          <label className="drawing-field">
            <span>Font</span>
            <select
              value={style.fontFamily ?? 'Arial'}
              disabled={locked}
              onChange={(event) => onUpdateStyle(selectedObject.id, { fontFamily: event.target.value })}
            >
              <option value="Arial">Arial</option>
              <option value="Helvetica">Helvetica</option>
              <option value="Inter">Inter</option>
              <option value="Times New Roman">Times New Roman</option>
              <option value="Courier New">Courier New</option>
            </select>
          </label>
          <label className="drawing-field drawing-field--split">
            <span>Font size</span>
            <input
              type="number"
              min={8}
              max={48}
              step={1}
              value={style.fontSize ?? 13}
              disabled={locked}
              onChange={(event) => onUpdateFontSize(selectedObject.id, event.target.value, onUpdateStyle)}
            />
          </label>
          <div className="drawing-inspector__button-row" aria-label="Text weight and style">
            <button
              className={metadata.fontWeight === '400' ? 'drawing-inspector__icon-button' : 'drawing-inspector__icon-button drawing-inspector__icon-button--active'}
              type="button"
              title="Bold"
              aria-pressed={metadata.fontWeight !== '400'}
              disabled={locked}
              onClick={() => onUpdateMetadata?.(selectedObject.id, { fontWeight: metadata.fontWeight === '400' ? '800' : '400' })}
            >
              <Bold size={15} />
              <span className="visually-hidden">Bold</span>
            </button>
            <button
              className={metadata.fontStyle === 'italic' ? 'drawing-inspector__icon-button drawing-inspector__icon-button--active' : 'drawing-inspector__icon-button'}
              type="button"
              title="Italic"
              aria-pressed={metadata.fontStyle === 'italic'}
              disabled={locked}
              onClick={() => onUpdateMetadata?.(selectedObject.id, { fontStyle: metadata.fontStyle === 'italic' ? 'normal' : 'italic' })}
            >
              <Italic size={15} />
              <span className="visually-hidden">Italic</span>
            </button>
          </div>
          <div className="drawing-segmented" aria-label="Text alignment">
            {(['left', 'center', 'right'] as const).map((align) => {
              const Icon = align === 'left' ? AlignLeft : align === 'center' ? AlignCenter : AlignRight;
              const active = textAlign(metadata) === align;
              return (
                <button
                  key={align}
                  className={active ? 'drawing-segmented__button drawing-segmented__button--active' : 'drawing-segmented__button'}
                  type="button"
                  title={`${align} align`}
                  aria-pressed={active}
                  disabled={locked}
                  onClick={() => onUpdateMetadata?.(selectedObject.id, { textAlign: align })}
                >
                  <Icon size={15} />
                  <span className="visually-hidden">{align} align</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {!isConnector ? (
        <div className="drawing-inspector__section">
          <h3>Object</h3>
          <button
            className="drawing-inspector__action-button drawing-inspector__action-button--danger"
            type="button"
            disabled={locked}
            onClick={() => onDeleteObject?.(selectedObject.id)}
          >
            <Trash2 size={15} />
            <span>Delete</span>
          </button>
        </div>
      ) : null}

      <div className="drawing-inspector__section">
        <h3>Source Document</h3>
        {linkedSourcePages.length === 0 ? (
          <p className="drawing-panel-empty">No source page is linked to this object yet.</p>
        ) : (
          <div className="drawing-source-link-list">
            {linkedSourcePages.slice(0, 3).map((page) => (
              <div className="drawing-source-link-card" key={page.id}>
                {apiBaseUrl ? (
                  <img
                    src={sourcePageImageUrl(apiBaseUrl, projectId, page, 96)}
                    alt={`${page.sourceFileId} page ${page.page} source preview`}
                    loading="lazy"
                  />
                ) : null}
                <div>
                  <strong>{page.sourceFileId}</strong>
                  <span>Page {page.page}</span>
                </div>
                <button type="button" onClick={() => onOpenSourcePage?.(page)} disabled={!onOpenSourcePage}>
                  <FileSearch size={14} />
                  <span>View source page</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

function NumberField({
  label,
  value,
  disabled,
  min,
  onChange,
}: {
  label: string;
  value: number;
  disabled: boolean;
  min?: number;
  onChange: (value: string) => void;
}) {
  const inputId = useId();
  return (
    <label className="drawing-field drawing-field--compact" htmlFor={inputId}>
      <span>{label}</span>
      <input
        id={inputId}
        type="number"
        min={min}
        step={1}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function sourcePagesForObject(object: DrawingObject, sourcePages: PageEvidence[]): PageEvidence[] {
  const byId = new Map(sourcePages.map((page) => [page.id, page]));
  const linked = new Map<string, PageEvidence>();
  for (const evidenceId of object.sourceEvidenceIds) {
    const page = byId.get(evidenceId);
    if (page) {
      linked.set(page.id, page);
    }
  }

  const sourceFileId = object.metadata?.sourceFileId;
  const pageNumber = object.metadata?.page;
  if (typeof sourceFileId === 'string' && (typeof pageNumber === 'number' || typeof pageNumber === 'string')) {
    const numericPage = typeof pageNumber === 'number' ? pageNumber : Number(pageNumber);
    const page = sourcePages.find((candidate) => candidate.sourceFileId === sourceFileId && candidate.page === numericPage);
    if (page) {
      linked.set(page.id, page);
    }
  }

  return Array.from(linked.values()).sort((left, right) => left.sourceFileId.localeCompare(right.sourceFileId) || left.page - right.page);
}

function updateBoundsNumber(
  object: DrawingObject,
  key: keyof DrawingBounds,
  value: string,
  onUpdateBounds?: (id: string, bounds: DrawingBounds) => void,
): void {
  const nextValue = Number(value);
  if (!Number.isFinite(nextValue)) {
    return;
  }
  const bounds = { ...object.bounds, [key]: key === 'width' || key === 'height' ? Math.max(8, nextValue) : nextValue };
  onUpdateBounds?.(object.id, bounds);
}

function sourcePageImageUrl(apiBaseUrl: string, projectId: string, page: PageEvidence, dpi: number): string {
  return `${apiBaseUrl}/projects/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(page.sourceFileId)}/pages/${page.page}/image?dpi=${dpi}`;
}

function ColorField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const colorInputValue = toColorInputValue(value);
  const colorInputId = useId();
  const textInputId = useId();

  return (
    <div className="drawing-field">
      <span>{label}</span>
      <span className="drawing-color-field">
        <label className="visually-hidden" htmlFor={colorInputId}>
          {label} color swatch
        </label>
        <input
          id={colorInputId}
          type="color"
          value={colorInputValue}
          disabled={disabled}
          title={`${label} color`}
          onChange={(event) => onChange(event.target.value)}
        />
        <label className="visually-hidden" htmlFor={textInputId}>
          {label} color value
        </label>
        <input id={textInputId} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
      </span>
    </div>
  );
}

function onUpdateNumber(
  id: string,
  key: 'strokeWidth' | 'opacity',
  value: string,
  onUpdateStyle: (id: string, style: Partial<DrawingStyle>) => void,
): void {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) {
    return;
  }
  onUpdateStyle(id, { [key]: key === 'opacity' ? Math.min(1, Math.max(0, numberValue)) : Math.max(0.25, numberValue) });
}

function onUpdateFontSize(
  id: string,
  value: string,
  onUpdateStyle: (id: string, style: Partial<DrawingStyle>) => void,
): void {
  const fontSize = Number(value);
  if (!Number.isFinite(fontSize)) {
    return;
  }
  onUpdateStyle(id, { fontSize: Math.min(48, Math.max(8, fontSize)) });
}

function dashPreset(dash: number[] | null | undefined): string {
  if (!dash || dash.length === 0) {
    return 'solid';
  }
  if (dash.length === 2 && dash[0] === 2 && dash[1] === 6) {
    return 'dotted';
  }
  if (dash.length === 4) {
    return 'dash-dot';
  }
  return 'dashed';
}

function dashForPreset(preset: string): number[] | null {
  if (preset === 'dashed') {
    return [10, 6];
  }
  if (preset === 'dotted') {
    return [2, 6];
  }
  if (preset === 'dash-dot') {
    return [12, 5, 2, 5];
  }
  return null;
}

function textAlign(metadata: Record<string, unknown>): 'left' | 'center' | 'right' {
  return metadata.textAlign === 'center' || metadata.textAlign === 'right' ? metadata.textAlign : 'left';
}

function toColorInputValue(value: string): string {
  return /^#[0-9a-f]{6}$/i.test(value) ? value : '#ffffff';
}
