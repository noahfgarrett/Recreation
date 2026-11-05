import { FileCode2, FileText, Focus, Hand, ListChecks, MousePointer2, Printer, Redo2, Route, Save, SquarePlus, Type, Undo2 } from 'lucide-react';
import type { DrawingCanvasMode } from './DrawingCanvas';

interface DrawingToolbarProps {
  mode: DrawingCanvasMode;
  objectCount: number;
  selectedLabel?: string | null;
  lineDraftActive?: boolean;
  onModeChange: (mode: DrawingCanvasMode) => void;
  onAddRegion: () => void;
  onSave?: () => void;
  onExportSvg?: () => void;
  onExportPdf?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  onFitView?: () => void;
  showPrintBoundary?: boolean;
  onTogglePrintBoundary?: () => void;
  hasLineTagRegister?: boolean;
  showLineTagRegister?: boolean;
  onToggleLineTagRegister?: () => void;
  className?: string;
}

export function DrawingToolbar({
  mode,
  objectCount,
  selectedLabel,
  lineDraftActive = false,
  onModeChange,
  onAddRegion,
  onSave,
  onExportSvg,
  onExportPdf,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  onFitView,
  showPrintBoundary = false,
  onTogglePrintBoundary,
  hasLineTagRegister = false,
  showLineTagRegister = false,
  onToggleLineTagRegister,
  className,
}: DrawingToolbarProps) {
  const hasFileActions = Boolean(onSave || onExportSvg || onExportPdf);

  return (
    <div className={`drawing-toolbar${className ? ` ${className}` : ''}`} role="toolbar" aria-label="Drawing tools">
      <div className="drawing-toolbar__group" aria-label="Canvas mode">
        <button
          className={mode === 'select' ? 'drawing-toolbar__button drawing-toolbar__button--active' : 'drawing-toolbar__button'}
          type="button"
          title="Select and move objects"
          aria-pressed={mode === 'select'}
          onClick={() => onModeChange('select')}
        >
          <MousePointer2 size={16} />
          <span className="visually-hidden">Select</span>
        </button>
        <button
          className={mode === 'pan' ? 'drawing-toolbar__button drawing-toolbar__button--active' : 'drawing-toolbar__button'}
          type="button"
          title="Pan mode"
          aria-pressed={mode === 'pan'}
          onClick={() => onModeChange('pan')}
        >
          <Hand size={16} />
          <span className="visually-hidden">Pan</span>
        </button>
      </div>

      <div className="drawing-toolbar__group" aria-label="Drawing edits">
        <button
          className={mode === 'line' ? 'drawing-toolbar__button drawing-toolbar__button--active' : 'drawing-toolbar__button'}
          type="button"
          title="Connect line"
          aria-pressed={mode === 'line'}
          onClick={() => onModeChange('line')}
        >
          <Route size={16} />
          <span className="visually-hidden">Connect line</span>
        </button>
        <button
          className={mode === 'text' ? 'drawing-toolbar__button drawing-toolbar__button--active' : 'drawing-toolbar__button'}
          type="button"
          title="Add text box"
          aria-pressed={mode === 'text'}
          onClick={() => onModeChange('text')}
        >
          <Type size={16} />
          <span className="visually-hidden">Add text box</span>
        </button>
        <button className="drawing-toolbar__button" type="button" title="Add region" onClick={onAddRegion}>
          <SquarePlus size={16} />
          <span className="visually-hidden">Add region</span>
        </button>
      </div>

      <div className="drawing-toolbar__group" aria-label="View and history">
        <button className="drawing-toolbar__button" type="button" title="Undo" onClick={onUndo} disabled={!canUndo}>
          <Undo2 size={16} />
          <span className="visually-hidden">Undo</span>
        </button>
        <button className="drawing-toolbar__button" type="button" title="Redo" onClick={onRedo} disabled={!canRedo}>
          <Redo2 size={16} />
          <span className="visually-hidden">Redo</span>
        </button>
        <button className="drawing-toolbar__button" type="button" title="Fit drawing" onClick={onFitView}>
          <Focus size={16} />
          <span className="visually-hidden">Fit drawing</span>
        </button>
        <button
          className={showPrintBoundary ? 'drawing-toolbar__button drawing-toolbar__button--active' : 'drawing-toolbar__button'}
          type="button"
          title={showPrintBoundary ? 'Hide print boundary' : 'Show print boundary'}
          aria-pressed={showPrintBoundary}
          onClick={onTogglePrintBoundary}
        >
          <Printer size={16} />
          <span className="visually-hidden">Print boundary</span>
        </button>
        {hasLineTagRegister ? (
          <button
            className={showLineTagRegister ? 'drawing-toolbar__button drawing-toolbar__button--active' : 'drawing-toolbar__button'}
            type="button"
            title={showLineTagRegister ? 'Hide line tag register' : 'Show line tag register'}
            aria-pressed={showLineTagRegister}
            onClick={onToggleLineTagRegister}
          >
            <ListChecks size={16} />
            <span className="visually-hidden">Line tag register</span>
          </button>
        ) : null}
      </div>

      {hasFileActions ? (
        <div className="drawing-toolbar__group" aria-label="Drawing file actions">
          {onSave ? (
            <button className="drawing-toolbar__button" type="button" title="Save drawing" onClick={onSave}>
              <Save size={16} />
              <span className="visually-hidden">Save drawing</span>
            </button>
          ) : null}
          {onExportSvg ? (
            <button className="drawing-toolbar__button" type="button" title="Export SVG" onClick={onExportSvg}>
              <FileCode2 size={16} />
              <span className="visually-hidden">Export SVG</span>
            </button>
          ) : null}
          {onExportPdf ? (
            <button className="drawing-toolbar__button" type="button" title="Export PDF" onClick={onExportPdf}>
              <FileText size={16} />
              <span className="visually-hidden">Export PDF</span>
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="drawing-toolbar__status" title={selectedLabel ? `Selected: ${selectedLabel}` : 'No object selected'}>
        <span>{objectCount} objects</span>
        <strong>{lineDraftActive ? 'Pick endpoint' : selectedLabel ?? 'No selection'}</strong>
      </div>
    </div>
  );
}
