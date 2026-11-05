import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import type { DrawingBounds, DrawingDocument, DrawingObject, DrawingPoint } from '../../types';
import { routeOrthogonal, screenToWorld } from './drawingGeometry';
import { PidSymbolShape } from './PidSymbolLibrary';
import { MIN_CANVAS_ZOOM, panViewport, useCanvasNavigation } from './useCanvasNavigation';

export type DrawingCanvasMode = 'select' | 'pan' | 'line' | 'text';

interface DrawingCanvasProps {
  drawing: DrawingDocument;
  selectedId: string | null;
  mode?: DrawingCanvasMode;
  hiddenLayerIds?: string[];
  showPrintBoundary?: boolean;
  showMinimap?: boolean;
  fitRequestId?: number;
  onSelectObject: (id: string | null) => void;
  onMoveObject: (id: string, dx: number, dy: number) => void;
  onLinePoint?: (point: DrawingPoint, objectId: string | null) => void;
  onCreateTextAt?: (point: DrawingPoint) => void;
  apiBaseUrl?: string | null;
  className?: string;
}

interface CanvasSize {
  width: number;
  height: number;
}

interface DragState {
  objectId: string;
  pointerId: number;
  lastWorldPoint: DrawingPoint;
  target: SVGElement;
}

interface ModePanState {
  pointerId: number;
  lastScreenPoint: DrawingPoint;
  target: SVGElement;
}

interface MinimapWindowState {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface MinimapInteractionState {
  mode: 'move' | 'resize';
  pointerId: number;
  startClientPoint: DrawingPoint;
  startWindow: MinimapWindowState;
  target: HTMLDivElement;
}

const FALLBACK_SIZE: CanvasSize = { width: 960, height: 640 };
const MINIMAP_DEFAULT_SIZE = { width: 248, height: 168 };
const MINIMAP_MIN_SIZE = { width: 190, height: 126 };
const MINIMAP_MARGIN = 10;
const OBJECT_LAYER_ORDER: Record<DrawingObject['kind'], number> = {
  source_fragment: 0,
  region: 1,
  pipe: 2,
  connector: 2,
  symbol: 3,
  label: 4,
};

export function DrawingCanvas({
  drawing,
  selectedId,
  mode = 'select',
  hiddenLayerIds = [],
  showPrintBoundary = false,
  showMinimap = false,
  fitRequestId = 0,
  onSelectObject,
  onMoveObject,
  onLinePoint,
  onCreateTextAt,
  apiBaseUrl,
  className,
}: DrawingCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const modePanRef = useRef<ModePanState | null>(null);
  const minimapInteractionRef = useRef<MinimapInteractionState | null>(null);
  const fittedDrawingKeyRef = useRef<string | null>(null);
  const size = useMeasuredSize(containerRef);
  const navigation = useCanvasNavigation({ x: 36, y: 36, zoom: 1 });
  const [minimapWindow, setMinimapWindow] = useState<MinimapWindowState | null>(null);
  const drawingWidth = finitePositive(drawing.width, 1200);
  const drawingHeight = finitePositive(drawing.height, 800);
  const hiddenLayerSet = useMemo(() => new Set(hiddenLayerIds), [hiddenLayerIds]);

  useEffect(() => {
    const drawingKey = `${drawing.id}:${drawingWidth}:${drawingHeight}:${size.width}:${size.height}`;
    if (fittedDrawingKeyRef.current === drawingKey) {
      return;
    }
    fittedDrawingKeyRef.current = drawingKey;
    const nextViewport = fitLargeDrawingViewport(drawingWidth, drawingHeight, size);
    if (nextViewport) {
      navigation.setViewport(nextViewport);
    }
  }, [drawing.id, drawingHeight, drawingWidth, navigation.setViewport, size]);

  useEffect(() => {
    if (fitRequestId <= 0) {
      return;
    }
    const nextViewport = fitLargeDrawingViewport(drawingWidth, drawingHeight, size);
    if (nextViewport) {
      navigation.setViewport(nextViewport);
    }
  }, [drawingHeight, drawingWidth, fitRequestId, navigation.setViewport, size]);

  useEffect(() => {
    const element = svgRef.current;
    if (!element) {
      return;
    }
    const handleWheel = (event: WheelEvent) => navigation.onNativeWheel(event, element);
    element.addEventListener('wheel', handleWheel, { passive: false });
    return () => element.removeEventListener('wheel', handleWheel);
  }, [navigation.onNativeWheel]);

  useEffect(() => {
    if (!showMinimap) {
      return;
    }
    setMinimapWindow((current) => {
      const initial = current ?? {
        x: MINIMAP_MARGIN,
        y: Math.max(MINIMAP_MARGIN, size.height - MINIMAP_DEFAULT_SIZE.height - MINIMAP_MARGIN),
        width: MINIMAP_DEFAULT_SIZE.width,
        height: MINIMAP_DEFAULT_SIZE.height,
      };
      return clampMinimapWindow(initial, size);
    });
  }, [showMinimap, size]);

  const orderedObjects = useMemo(
    () =>
      [...drawing.objects].sort(
        (left, right) => OBJECT_LAYER_ORDER[left.kind] - OBJECT_LAYER_ORDER[right.kind],
      ).filter((object) => isObjectVisible(object, hiddenLayerSet)),
    [drawing.objects, hiddenLayerSet],
  );
  const sourceImageBaseUrl = useMemo(() => {
    if (!apiBaseUrl) {
      return null;
    }
    return `${apiBaseUrl}/projects/${encodeURIComponent(drawing.projectId)}/sources`;
  }, [apiBaseUrl, drawing.projectId]);

  const screenPointForEvent = useCallback(
    (event: ReactPointerEvent<SVGElement>): DrawingPoint => {
      const svg = svgRef.current;
      const rect = svg?.getBoundingClientRect();
      if (!rect || rect.width <= 0 || rect.height <= 0) {
        return { x: event.clientX, y: event.clientY };
      }

      return {
        x: ((event.clientX - rect.left) / rect.width) * size.width,
        y: ((event.clientY - rect.top) / rect.height) * size.height,
      };
    },
    [size.height, size.width],
  );

  const worldPointForEvent = useCallback(
    (event: ReactPointerEvent<SVGElement>): DrawingPoint => {
      return screenToWorld(screenPointForEvent(event), navigation.viewport);
    },
    [navigation.viewport, screenPointForEvent],
  );

  const stopDragging = useCallback((event: ReactPointerEvent<SVGElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }

    releasePointerCapture(drag.target, drag.pointerId);
    dragRef.current = null;
  }, []);

  const startModePanning = useCallback(
    (event: ReactPointerEvent<SVGElement>) => {
      if (mode !== 'pan' || event.button !== 0) {
        return false;
      }

      event.preventDefault();
      capturePointer(event.currentTarget, event.pointerId);
      modePanRef.current = {
        pointerId: event.pointerId,
        lastScreenPoint: screenPointForEvent(event),
        target: event.currentTarget,
      };
      return true;
    },
    [mode, screenPointForEvent],
  );

  const stopModePanning = useCallback((event: ReactPointerEvent<SVGElement>) => {
    const modePan = modePanRef.current;
    if (!modePan || modePan.pointerId !== event.pointerId) {
      return;
    }

    releasePointerCapture(modePan.target, modePan.pointerId);
    modePanRef.current = null;
  }, []);

  const handleCanvasPointerDown = useCallback(
    (event: ReactPointerEvent<SVGSVGElement>) => {
      navigation.onPointerDown(event);
      if (event.button === 0 && mode === 'text') {
        event.preventDefault();
        onCreateTextAt?.(worldPointForEvent(event));
        return;
      }

      if (event.button === 0 && mode === 'line') {
        event.preventDefault();
        onLinePoint?.(worldPointForEvent(event), null);
        return;
      }

      if (event.button === 0) {
        onSelectObject(null);
        startModePanning(event);
      }
    },
    [mode, navigation, onCreateTextAt, onLinePoint, onSelectObject, startModePanning, worldPointForEvent],
  );

  const handleCanvasPointerMove = useCallback(
    (event: ReactPointerEvent<SVGSVGElement>) => {
      navigation.onPointerMove(event);
      const modePan = modePanRef.current;
      if (modePan && modePan.pointerId === event.pointerId) {
        event.preventDefault();
        const nextScreenPoint = screenPointForEvent(event);
        const dx = nextScreenPoint.x - modePan.lastScreenPoint.x;
        const dy = nextScreenPoint.y - modePan.lastScreenPoint.y;
        modePanRef.current = { ...modePan, lastScreenPoint: nextScreenPoint };
        navigation.setViewport((current) => panViewport(current, dx, dy));
        return;
      }

      const drag = dragRef.current;
      if (!drag || drag.pointerId !== event.pointerId) {
        return;
      }

      event.preventDefault();
      const nextWorldPoint = worldPointForEvent(event);
      const dx = nextWorldPoint.x - drag.lastWorldPoint.x;
      const dy = nextWorldPoint.y - drag.lastWorldPoint.y;
      if (Number.isFinite(dx) && Number.isFinite(dy) && (dx !== 0 || dy !== 0)) {
        dragRef.current = { ...drag, lastWorldPoint: nextWorldPoint };
        onMoveObject(drag.objectId, dx, dy);
      }
    },
    [navigation, onMoveObject, screenPointForEvent, worldPointForEvent],
  );

  const handleCanvasPointerUp = useCallback(
    (event: ReactPointerEvent<SVGSVGElement>) => {
      navigation.onPointerUp(event);
      stopDragging(event);
      stopModePanning(event);
    },
    [navigation, stopDragging, stopModePanning],
  );

  const handleCanvasPointerCancel = useCallback(
    (event: ReactPointerEvent<SVGSVGElement>) => {
      navigation.onPointerCancel(event);
      stopDragging(event);
      stopModePanning(event);
    },
    [navigation, stopDragging, stopModePanning],
  );

  const updateMinimapInteraction = useCallback(
    (clientX: number, clientY: number) => {
      const interaction = minimapInteractionRef.current;
      if (!interaction) {
        return;
      }
      const dx = clientX - interaction.startClientPoint.x;
      const dy = clientY - interaction.startClientPoint.y;
      const next =
        interaction.mode === 'move'
          ? {
              ...interaction.startWindow,
              x: interaction.startWindow.x + dx,
              y: interaction.startWindow.y + dy,
            }
          : {
              ...interaction.startWindow,
              width: interaction.startWindow.width + dx,
              height: interaction.startWindow.height + dy,
            };
      setMinimapWindow(clampMinimapWindow(next, size));
    },
    [size],
  );

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      const interaction = minimapInteractionRef.current;
      if (!interaction || interaction.pointerId < 0 || interaction.pointerId !== event.pointerId) {
        return;
      }
      event.preventDefault();
      updateMinimapInteraction(event.clientX, event.clientY);
    };
    const handleMouseMove = (event: MouseEvent) => {
      const interaction = minimapInteractionRef.current;
      if (!interaction || interaction.pointerId !== -1) {
        return;
      }
      event.preventDefault();
      updateMinimapInteraction(event.clientX, event.clientY);
    };
    const stop = () => {
      minimapInteractionRef.current = null;
    };
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', stop);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', stop);
    };
  }, [updateMinimapInteraction]);

  const startMinimapInteraction = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>, mode: 'move' | 'resize') => {
      if (!minimapWindow) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      minimapInteractionRef.current = {
        mode,
        pointerId: event.pointerId,
        startClientPoint: { x: event.clientX, y: event.clientY },
        startWindow: minimapWindow,
        target: event.currentTarget,
      };
    },
    [minimapWindow],
  );

  const startMinimapMouseInteraction = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>, mode: 'move' | 'resize') => {
      if (!minimapWindow) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      minimapInteractionRef.current = {
        mode,
        pointerId: -1,
        startClientPoint: { x: event.clientX, y: event.clientY },
        startWindow: minimapWindow,
        target: event.currentTarget,
      };
    },
    [minimapWindow],
  );

  const handleMinimapPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const interaction = minimapInteractionRef.current;
      if (!interaction || interaction.pointerId !== event.pointerId) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      updateMinimapInteraction(event.clientX, event.clientY);
    },
    [updateMinimapInteraction],
  );

  const stopMinimapInteraction = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const interaction = minimapInteractionRef.current;
    if (!interaction || interaction.pointerId !== event.pointerId) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    interaction.target.releasePointerCapture?.(interaction.pointerId);
    minimapInteractionRef.current = null;
  }, []);

  const handleObjectPointerDown = useCallback(
    (event: ReactPointerEvent<SVGGElement>, object: DrawingObject) => {
      if (event.button !== 0) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      if (mode === 'text') {
        onCreateTextAt?.(worldPointForEvent(event));
        return;
      }

      onSelectObject(object.id);

      if (mode === 'line') {
        onLinePoint?.(connectionPointForObject(object), object.id);
        return;
      }

      if (startModePanning(event) || object.locked) {
        return;
      }

      capturePointer(event.currentTarget, event.pointerId);
      dragRef.current = {
        objectId: object.id,
        pointerId: event.pointerId,
        lastWorldPoint: worldPointForEvent(event),
        target: event.currentTarget,
      };
    },
    [mode, onCreateTextAt, onLinePoint, onSelectObject, startModePanning, worldPointForEvent],
  );

  const classNames = [
    'drawing-canvas',
    mode === 'pan' ? 'drawing-canvas--pan-mode' : '',
    mode === 'line' ? 'drawing-canvas--line-mode' : '',
    mode === 'text' ? 'drawing-canvas--text-mode' : '',
    navigation.isPanning || modePanRef.current ? 'drawing-canvas--panning' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classNames} ref={containerRef}>
      <svg
        ref={svgRef}
        className="drawing-canvas__svg"
        role="img"
        aria-label={`${drawing.name} drawing canvas`}
        viewBox={`0 0 ${size.width} ${size.height}`}
        preserveAspectRatio="none"
        onPointerDown={handleCanvasPointerDown}
        onPointerMove={handleCanvasPointerMove}
        onPointerUp={handleCanvasPointerUp}
        onPointerCancel={handleCanvasPointerCancel}
      >
        <title>{drawing.name}</title>
        <rect className="drawing-canvas__screen-bg" x={0} y={0} width={size.width} height={size.height} />
        <g
          className="drawing-canvas__world"
          transform={`translate(${navigation.viewport.x} ${navigation.viewport.y}) scale(${navigation.viewport.zoom})`}
        >
          <rect
            className="drawing-canvas__sheet"
            x={0}
            y={0}
            width={drawingWidth}
            height={drawingHeight}
            vectorEffect="non-scaling-stroke"
          />
          {showPrintBoundary ? <PrintBoundary drawingWidth={drawingWidth} drawingHeight={drawingHeight} /> : null}
          {orderedObjects.map((object) => (
            <DrawingObjectSvg
              key={object.id}
              object={object}
              selected={object.id === selectedId}
              sourceImageBaseUrl={sourceImageBaseUrl}
              onSelect={onSelectObject}
              onPointerDown={handleObjectPointerDown}
            />
          ))}
        </g>
      </svg>
      <div className="drawing-canvas__hud" aria-hidden="true">
        <span>{Math.round(navigation.viewport.zoom * 100)}%</span>
        <span>
          {drawing.objects.length} object{drawing.objects.length === 1 ? '' : 's'}
        </span>
      </div>
      {showMinimap ? (
        <FloatingMinimap
          windowState={minimapWindow}
          drawingWidth={drawingWidth}
          drawingHeight={drawingHeight}
          objects={orderedObjects}
          viewport={navigation.viewport}
          size={size}
          onMoveStart={(event) => startMinimapInteraction(event, 'move')}
          onResizeStart={(event) => startMinimapInteraction(event, 'resize')}
          onMouseMoveStart={(event) => startMinimapMouseInteraction(event, 'move')}
          onMouseResizeStart={(event) => startMinimapMouseInteraction(event, 'resize')}
          onPointerMove={handleMinimapPointerMove}
          onPointerUp={stopMinimapInteraction}
          onPointerCancel={stopMinimapInteraction}
        />
      ) : null}
    </div>
  );
}

function PrintBoundary({ drawingWidth, drawingHeight }: { drawingWidth: number; drawingHeight: number }) {
  const margin = Math.max(36, Math.min(drawingWidth, drawingHeight) * 0.025);
  return (
    <g className="drawing-canvas__print-boundary" aria-hidden="true">
      <rect
        x={margin}
        y={margin}
        width={Math.max(1, drawingWidth - margin * 2)}
        height={Math.max(1, drawingHeight - margin * 2)}
        vectorEffect="non-scaling-stroke"
      />
      <text x={margin + 10} y={margin + 18} vectorEffect="non-scaling-stroke">
        PRINT AREA
      </text>
    </g>
  );
}

function FloatingMinimap({
  windowState,
  drawingWidth,
  drawingHeight,
  objects,
  viewport,
  size,
  onMoveStart,
  onResizeStart,
  onMouseMoveStart,
  onMouseResizeStart,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
}: {
  windowState: MinimapWindowState | null;
  drawingWidth: number;
  drawingHeight: number;
  objects: DrawingObject[];
  viewport: { x: number; y: number; zoom: number };
  size: CanvasSize;
  onMoveStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onResizeStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onMouseMoveStart: (event: ReactMouseEvent<HTMLDivElement>) => void;
  onMouseResizeStart: (event: ReactMouseEvent<HTMLDivElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onPointerUp: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onPointerCancel: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  if (!windowState) {
    return null;
  }
  return (
    <div
      className="drawing-minimap-window"
      style={{
        transform: `translate(${windowState.x}px, ${windowState.y}px)`,
        width: windowState.width,
        height: windowState.height,
      }}
      aria-label="Drawing minimap window"
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
    >
      <div
        className="drawing-minimap-window__header"
        onPointerDown={onMoveStart}
        onMouseDown={onMouseMoveStart}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        role="button"
        tabIndex={0}
        aria-label="Move minimap"
      >
        <span>Map</span>
        <b>{Math.round(viewport.zoom * 100)}%</b>
      </div>
      <DrawingMinimap
        drawingWidth={drawingWidth}
        drawingHeight={drawingHeight}
        objects={objects}
        viewport={viewport}
        size={size}
      />
      <div
        className="drawing-minimap-window__resize"
        onPointerDown={onResizeStart}
        onMouseDown={onMouseResizeStart}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        role="separator"
        aria-label="Resize minimap"
      />
    </div>
  );
}

function DrawingMinimap({
  drawingWidth,
  drawingHeight,
  objects,
  viewport,
  size,
}: {
  drawingWidth: number;
  drawingHeight: number;
  objects: DrawingObject[];
  viewport: { x: number; y: number; zoom: number };
  size: CanvasSize;
}) {
  const viewportBox = useMemo(() => {
    const zoom = Math.max(MIN_CANVAS_ZOOM, viewport.zoom);
    return {
      x: Math.max(0, -viewport.x / zoom),
      y: Math.max(0, -viewport.y / zoom),
      width: Math.min(drawingWidth, size.width / zoom),
      height: Math.min(drawingHeight, size.height / zoom),
    };
  }, [drawingHeight, drawingWidth, size.height, size.width, viewport.x, viewport.y, viewport.zoom]);

  return (
    <svg
      className="drawing-minimap"
      viewBox={`0 0 ${drawingWidth} ${drawingHeight}`}
      preserveAspectRatio="xMidYMid meet"
      aria-label="Drawing minimap"
    >
      <rect className="drawing-minimap__sheet" x={0} y={0} width={drawingWidth} height={drawingHeight} />
      {objects.slice(0, 900).map((object) => {
        if ((object.kind === 'pipe' || object.kind === 'connector') && object.points.length >= 2) {
          return (
            <polyline
              key={object.id}
              className={`drawing-minimap__object drawing-minimap__object--${object.kind}`}
              points={object.points.map((point) => `${finiteNumber(point.x)},${finiteNumber(point.y)}`).join(' ')}
              vectorEffect="non-scaling-stroke"
            />
          );
        }
        const bounds = normalizeBounds(object.bounds);
        const width = Math.max(bounds.width, object.kind === 'symbol' ? 12 : 3);
        const height = Math.max(bounds.height, object.kind === 'symbol' ? 12 : 3);
        if (width <= 0 || height <= 0) {
          return null;
        }
        return (
          <rect
            key={object.id}
            className={`drawing-minimap__object drawing-minimap__object--${object.kind}`}
            x={bounds.x}
            y={bounds.y}
            width={width}
            height={height}
          />
        );
      })}
      <rect className="drawing-minimap__viewport" x={viewportBox.x} y={viewportBox.y} width={viewportBox.width} height={viewportBox.height} />
    </svg>
  );
}

function clampMinimapWindow(windowState: MinimapWindowState, size: CanvasSize): MinimapWindowState {
  const maxWidth = Math.max(MINIMAP_MIN_SIZE.width, Math.min(420, size.width - MINIMAP_MARGIN * 2));
  const maxHeight = Math.max(MINIMAP_MIN_SIZE.height, Math.min(300, size.height - MINIMAP_MARGIN * 2));
  const width = clamp(windowState.width, MINIMAP_MIN_SIZE.width, maxWidth);
  const height = clamp(windowState.height, MINIMAP_MIN_SIZE.height, maxHeight);
  return {
    x: clamp(windowState.x, MINIMAP_MARGIN, Math.max(MINIMAP_MARGIN, size.width - width - MINIMAP_MARGIN)),
    y: clamp(windowState.y, MINIMAP_MARGIN, Math.max(MINIMAP_MARGIN, size.height - height - MINIMAP_MARGIN)),
    width,
    height,
  };
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

function DrawingObjectSvg({
  object,
  selected,
  sourceImageBaseUrl,
  onSelect,
  onPointerDown,
}: {
  object: DrawingObject;
  selected: boolean;
  sourceImageBaseUrl: string | null;
  onSelect: (id: string) => void;
  onPointerDown: (event: ReactPointerEvent<SVGGElement>, object: DrawingObject) => void;
}) {
  const label = object.label.trim();
  const className = [
    'drawing-object',
    `drawing-object--${object.kind}`,
    selected ? 'drawing-object--selected' : '',
    object.locked ? 'drawing-object--locked' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <g
      className={className}
      role="button"
      aria-label={objectAriaLabel(object)}
      tabIndex={0}
      onKeyDown={(event: ReactKeyboardEvent<SVGGElement>) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect(object.id);
        }
      }}
      onPointerDown={(event) => onPointerDown(event, object)}
    >
      <title>{objectAriaLabel(object)}</title>
      {renderObjectShape(object, selected, sourceImageBaseUrl)}
      {label && object.kind !== 'label' && object.metadata?.hideCenterLabel !== true ? <ObjectLabel object={object} /> : null}
    </g>
  );
}

function renderObjectShape(object: DrawingObject, selected: boolean, sourceImageBaseUrl: string | null) {
  switch (object.kind) {
    case 'source_fragment':
      return <SourceFragment object={object} selected={selected} sourceImageBaseUrl={sourceImageBaseUrl} />;
    case 'region':
      return <Region object={object} selected={selected} />;
    case 'pipe':
    case 'connector':
      return <Connector object={object} selected={selected} />;
    case 'label':
      return <TextLabel object={object} selected={selected} />;
    case 'symbol':
      return <SymbolObject object={object} selected={selected} />;
  }
}

function isObjectVisible(object: DrawingObject, hiddenLayers: Set<string>): boolean {
  if (hiddenLayers.size === 0) {
    return true;
  }
  return objectLayerIds(object).every((layer) => !hiddenLayers.has(layer));
}

export function objectLayerIds(object: DrawingObject): string[] {
  const layers = new Set<string>();
  if (object.kind === 'source_fragment' || object.metadata?.sourceVector === true || object.metadata?.sourceDerived === true) {
    layers.add('source');
  }
  if (object.metadata?.semanticOverlay === true) {
    layers.add('semantic');
  }
  if (object.kind === 'region' || object.metadata?.sourceGeneratedDetailBox || object.metadata?.sourceGeneratedInventory) {
    layers.add('zones');
  }
  if (object.kind === 'pipe' || object.kind === 'connector') {
    layers.add('lines');
  }
  if (object.kind === 'symbol') {
    layers.add('symbols');
  }
  if (object.kind === 'label') {
    layers.add('labels');
  }
  if (object.metadata?.sourceGeneratedCoverageIndex === true) {
    layers.add('coverage');
  }
  if (object.metadata?.edgeContinuation === true || object.metadata?.sourceCandidateId || object.metadata?.presentationContinuationRack === true) {
    layers.add('continuations');
  }
  if (object.metadata?.presentationRouteBundle === true || object.metadata?.sourceGeneratedRoutingPolish === true) {
    layers.add('routing');
  }
  if (layers.size === 0) {
    layers.add('drafting');
  }
  return Array.from(layers);
}

function SourceFragment({
  object,
  selected,
  sourceImageBaseUrl,
}: {
  object: DrawingObject;
  selected: boolean;
  sourceImageBaseUrl: string | null;
}) {
  const bounds = normalizeBounds(object.bounds);
  const stroke = object.style.stroke || 'var(--rec-border-strong)';
  const fill = object.style.fill || 'transparent';
  const imageUrl = sourceFragmentImageUrl(object, sourceImageBaseUrl);

  return (
    <>
      {selected ? <SelectionRect bounds={bounds} /> : null}
      {imageUrl ? (
        <image
          className="drawing-canvas__source-image"
          href={imageUrl}
          x={bounds.x}
          y={bounds.y}
          width={bounds.width}
          height={bounds.height}
          opacity={safeOpacity(object.style.opacity, 0.42)}
          preserveAspectRatio="none"
        />
      ) : null}
      <rect
        className="drawing-canvas__source-fragment"
        x={bounds.x}
        y={bounds.y}
        width={bounds.width}
        height={bounds.height}
        fill={fill}
        stroke={stroke}
        strokeWidth={Math.max(1, object.style.strokeWidth || 1)}
        strokeDasharray={dashArray(object.style.dash) ?? '8 5'}
        opacity={safeOpacity(object.style.opacity, 0.42)}
        vectorEffect="non-scaling-stroke"
      />
      {object.label ? (
        <text
          className="drawing-canvas__source-label"
          x={bounds.x + 8}
          y={bounds.y + 16}
          fontSize={Math.max(10, object.style.fontSize ?? 12)}
          fontFamily={object.style.fontFamily ?? 'var(--rec-font-mono)'}
        >
          {object.label}
        </text>
      ) : null}
    </>
  );
}

function Region({ object, selected }: { object: DrawingObject; selected: boolean }) {
  const bounds = normalizeBounds(object.bounds);
  const stroke = object.style.stroke || 'var(--rec-info)';
  const fill = object.style.fill || 'rgba(59, 130, 246, 0.12)';

  return (
    <>
      {selected ? <SelectionRect bounds={bounds} /> : null}
      <rect
        className="drawing-canvas__region"
        x={bounds.x}
        y={bounds.y}
        width={bounds.width}
        height={bounds.height}
        fill={fill}
        stroke={stroke}
        strokeWidth={Math.max(1, object.style.strokeWidth || 1)}
        opacity={safeOpacity(object.style.opacity, 0.72)}
        vectorEffect="non-scaling-stroke"
      />
    </>
  );
}

function Connector({ object, selected }: { object: DrawingObject; selected: boolean }) {
  const points = connectorPoints(object);
  if (points.length < 2) {
    return null;
  }

  const stroke = object.style.stroke || connectorFallbackStroke(object);
  const strokeWidth = Math.max(1.5, object.style.strokeWidth || 2);
  const pointList = pointsToPolyline(points);
  const arrowStart = object.metadata?.arrowStart === true;
  const arrowEnd = object.metadata?.arrowEnd === true;
  const visualPoints = trimPointsForArrowheads(points, arrowStart, arrowEnd, Math.max(9, strokeWidth * 4.8));
  const visualPointList = pointsToPolyline(visualPoints);

  return (
    <>
      <polyline
        className="drawing-canvas__hit-path"
        points={pointList}
        fill="none"
        stroke="transparent"
        strokeWidth={Math.max(12, strokeWidth + 10)}
        vectorEffect="non-scaling-stroke"
      />
      {selected ? (
        <polyline
          className="drawing-canvas__selection-path"
          points={pointList}
          fill="none"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      <polyline
        className="drawing-canvas__connector"
        points={visualPointList}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeDasharray={dashArray(object.style.dash)}
        opacity={safeOpacity(object.style.opacity, 1)}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      {arrowStart ? <ConnectorArrowhead points={points} at="start" stroke={stroke} strokeWidth={strokeWidth} opacity={safeOpacity(object.style.opacity, 1)} /> : null}
      {arrowEnd ? <ConnectorArrowhead points={points} at="end" stroke={stroke} strokeWidth={strokeWidth} opacity={safeOpacity(object.style.opacity, 1)} /> : null}
    </>
  );
}

function ConnectorArrowhead({
  points,
  at,
  stroke,
  strokeWidth,
  opacity,
}: {
  points: DrawingPoint[];
  at: 'start' | 'end';
  stroke: string;
  strokeWidth: number;
  opacity: number;
}) {
  const head = connectorArrowheadPoints(points, at, Math.max(9, strokeWidth * 4.8), Math.max(7, strokeWidth * 3.4));
  if (!head) {
    return null;
  }
  return (
    <polygon
      className="drawing-canvas__connector-arrowhead"
      points={pointsToPolyline(head)}
      fill={stroke}
      stroke={stroke}
      strokeWidth={Math.max(0.8, strokeWidth * 0.35)}
      opacity={opacity}
      strokeLinejoin="round"
      vectorEffect="non-scaling-stroke"
    />
  );
}

function TextLabel({ object, selected }: { object: DrawingObject; selected: boolean }) {
  const bounds = labelBounds(object);
  const fontSize = Math.max(9, object.style.fontSize ?? 13);
  const fill = object.style.stroke || 'var(--rec-text)';
  const isTextBox = object.metadata?.textBox === true;
  const textAlign = textAlignment(object);
  const textX = textAnchorX(bounds, textAlign);
  const textAnchor = svgTextAnchor(textAlign);
  const fontWeight = object.metadata?.fontWeight === '400' ? 400 : 800;
  const fontStyle = object.metadata?.fontStyle === 'italic' ? 'italic' : 'normal';
  const rotationDegrees = typeof object.metadata?.rotationDegrees === 'number' ? object.metadata.rotationDegrees : 0;
  const lines = wrappedTextLines(object.label, bounds.width, bounds.height, fontSize, object.metadata?.textWrap === true);
  const lineHeight = fontSize * 1.18;
  const hitWidth = Math.max(bounds.width, Math.max(...lines.map((line) => line.length), 1) * fontSize * 0.58);
  const hitHeight = Math.max(bounds.height, lines.length * lineHeight + 6);
  const textY = bounds.y + fontSize;
  const transform = Math.abs(rotationDegrees) > 0.5 ? `rotate(${rotationDegrees} ${textX} ${textY})` : undefined;

  return (
    <>
      {isTextBox ? (
        <rect
          className="drawing-canvas__text-box-bg"
          x={bounds.x}
          y={bounds.y}
          width={hitWidth}
          height={hitHeight}
          rx={3}
          fill={object.style.fill || '#ffffff'}
          stroke={typeof object.metadata?.boxStroke === 'string' ? object.metadata.boxStroke : '#cbd5e1'}
          strokeWidth={1}
          opacity={safeOpacity(object.style.opacity, 1)}
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      <rect
        className="drawing-canvas__label-hit"
        x={bounds.x}
        y={bounds.y}
        width={hitWidth}
        height={hitHeight}
        fill="transparent"
      />
      {selected ? <SelectionRect bounds={bounds} minWidth={hitWidth} minHeight={hitHeight} /> : null}
      <text
        className="drawing-canvas__text-label"
        x={textX}
        y={textY}
        fill={fill}
        fontSize={fontSize}
        fontFamily={object.style.fontFamily ?? 'var(--rec-font-mono)'}
        fontWeight={fontWeight}
        fontStyle={fontStyle}
        textAnchor={textAnchor}
        opacity={safeOpacity(object.style.opacity, 1)}
        transform={transform}
      >
        {lines.map((line, index) => (
          <tspan key={`${object.id}-line-${index}`} x={textX} dy={index === 0 ? 0 : lineHeight}>
            {line}
          </tspan>
        ))}
      </text>
    </>
  );
}

function connectionPointForObject(object: DrawingObject): DrawingPoint {
  if ((object.kind === 'pipe' || object.kind === 'connector') && object.points.length > 0) {
    return object.points[object.points.length - 1];
  }
  const bounds = normalizeBounds(object.bounds);
  return {
    x: bounds.x + bounds.width / 2,
    y: bounds.y + bounds.height / 2,
  };
}

function textAlignment(object: DrawingObject): 'left' | 'center' | 'right' {
  const align = object.metadata?.textAlign;
  return align === 'center' || align === 'right' ? align : 'left';
}

function textAnchorX(bounds: DrawingBounds, align: 'left' | 'center' | 'right'): number {
  if (align === 'center') {
    return bounds.x + bounds.width / 2;
  }
  if (align === 'right') {
    return bounds.x + bounds.width;
  }
  return bounds.x;
}

function svgTextAnchor(align: 'left' | 'center' | 'right'): 'start' | 'middle' | 'end' {
  if (align === 'center') {
    return 'middle';
  }
  return align === 'right' ? 'end' : 'start';
}

function SymbolObject({ object, selected }: { object: DrawingObject; selected: boolean }) {
  const bounds = normalizeBounds(object.bounds);
  const stroke = object.style.stroke || 'var(--rec-node-unknown-border)';
  const fill = object.style.fill || 'var(--rec-node-unknown-bg)';
  const symbolType = typeof object.metadata?.symbolType === 'string' ? object.metadata.symbolType : 'equipment';
  const orientation = typeof object.metadata?.orientation === 'string' ? object.metadata.orientation : 'right';

  return (
    <>
      {selected ? <SelectionRect bounds={bounds} /> : null}
      <SymbolShape bounds={bounds} stroke={stroke} fill={fill} strokeWidth={Math.max(1.25, object.style.strokeWidth || 1.5)} opacity={safeOpacity(object.style.opacity, 1)} symbolType={symbolType} orientation={orientation} />
    </>
  );
}

function SymbolShape({
  bounds,
  stroke,
  fill,
  strokeWidth,
  opacity,
  symbolType,
  orientation,
}: {
  bounds: DrawingBounds;
  stroke: string;
  fill: string;
  strokeWidth: number;
  opacity: number;
  symbolType: string;
  orientation: string;
}) {
  return (
    <PidSymbolShape
      bounds={bounds}
      fill={fill}
      opacity={opacity}
      orientation={orientation as 'left' | 'right' | 'vertical' | 'horizontal'}
      stroke={stroke}
      strokeWidth={strokeWidth}
      symbolType={symbolType}
    />
  );
}

function ObjectLabel({ object }: { object: DrawingObject }) {
  const anchor = labelAnchor(object);
  const fontSize = Math.max(9, object.style.fontSize ?? 11);

  return (
    <text
      className="drawing-canvas__object-label"
      x={anchor.x}
      y={anchor.y}
      textAnchor="middle"
      fontSize={fontSize}
      fontFamily={object.style.fontFamily ?? 'var(--rec-font-mono)'}
    >
      {object.label}
    </text>
  );
}

function SelectionRect({
  bounds,
  minWidth = 0,
  minHeight = 0,
}: {
  bounds: DrawingBounds;
  minWidth?: number;
  minHeight?: number;
}) {
  const width = Math.max(bounds.width, minWidth, 8);
  const height = Math.max(bounds.height, minHeight, 8);

  return (
    <rect
      className="drawing-canvas__selection-rect"
      x={bounds.x - 4}
      y={bounds.y - 4}
      width={width + 8}
      height={height + 8}
      vectorEffect="non-scaling-stroke"
    />
  );
}

function useMeasuredSize(ref: React.RefObject<HTMLElement | null>): CanvasSize {
  const [size, setSize] = useState<CanvasSize>(FALLBACK_SIZE);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }

    const measure = () => {
      const rect = element.getBoundingClientRect();
      const next = {
        width: finitePositive(rect.width, FALLBACK_SIZE.width),
        height: finitePositive(rect.height, FALLBACK_SIZE.height),
      };
      setSize((current) => (current.width === next.width && current.height === next.height ? current : next));
    };

    measure();

    if (typeof ResizeObserver === 'undefined') {
      return;
    }

    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return size;
}

function connectorPoints(object: DrawingObject): DrawingPoint[] {
  if (object.metadata?.templateDerived === true || object.metadata?.preserveGeometry === true) {
    return object.points;
  }
  if (object.points.length === 2) {
    return routeOrthogonal(object.points[0], object.points[1]);
  }
  return object.points;
}

function pointsToPolyline(points: DrawingPoint[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(' ');
}

function trimPointsForArrowheads(
  points: DrawingPoint[],
  trimStart: boolean,
  trimEnd: boolean,
  length: number,
): DrawingPoint[] {
  if (points.length < 2 || length <= 0) {
    return points;
  }
  const next = points.map((point) => ({ ...point }));
  if (trimStart) {
    next[0] = pointMovedToward(next[0], next[1], length);
  }
  if (trimEnd) {
    next[next.length - 1] = pointMovedToward(next[next.length - 1], next[next.length - 2], length);
  }
  return next;
}

function pointMovedToward(point: DrawingPoint, neighbor: DrawingPoint, distance: number): DrawingPoint {
  const dx = neighbor.x - point.x;
  const dy = neighbor.y - point.y;
  const magnitude = Math.hypot(dx, dy);
  if (magnitude <= distance || magnitude < 0.01) {
    return point;
  }
  return { x: point.x + (dx / magnitude) * distance, y: point.y + (dy / magnitude) * distance };
}

function connectorArrowheadPoints(
  points: DrawingPoint[],
  at: 'start' | 'end',
  length: number,
  width: number,
): DrawingPoint[] | null {
  if (points.length < 2) {
    return null;
  }
  const tip = at === 'end' ? points[points.length - 1] : points[0];
  const neighbor = at === 'end' ? points[points.length - 2] : points[1];
  const dx = tip.x - neighbor.x;
  const dy = tip.y - neighbor.y;
  const magnitude = Math.hypot(dx, dy);
  if (magnitude < 0.01) {
    return null;
  }
  const ux = dx / magnitude;
  const uy = dy / magnitude;
  const base = { x: tip.x - ux * length, y: tip.y - uy * length };
  const px = -uy * (width / 2);
  const py = ux * (width / 2);
  return [tip, { x: base.x + px, y: base.y + py }, { x: base.x - px, y: base.y - py }];
}

function wrappedTextLines(label: string, width: number, height: number, fontSize: number, forceWrap: boolean): string[] {
  const clean = label.trim().replace(/\s+/g, ' ');
  if (!clean) {
    return [''];
  }
  const maxChars = Math.max(4, Math.floor(Math.max(1, width - 4) / Math.max(1, fontSize * 0.54)));
  if (!forceWrap && clean.length <= maxChars) {
    return [clean];
  }
  const lines: string[] = [];
  let current = '';
  for (const word of clean.split(' ')) {
    if (word.length > maxChars) {
      if (current) {
        lines.push(current);
        current = '';
      }
      for (let start = 0; start < word.length; start += maxChars) {
        lines.push(word.slice(start, start + maxChars));
      }
      continue;
    }
    const proposed = current ? `${current} ${word}` : word;
    if (proposed.length <= maxChars) {
      current = proposed;
    } else {
      if (current) {
        lines.push(current);
      }
      current = word;
    }
  }
  if (current) {
    lines.push(current);
  }
  const maxLines = Math.max(1, Math.floor(Math.max(height, fontSize * 1.4) / Math.max(fontSize * 1.18, 1)));
  return lines.slice(0, maxLines);
}

function labelAnchor(object: DrawingObject): DrawingPoint {
  if (object.kind === 'pipe' || object.kind === 'connector') {
    const points = connectorPoints(object);
    if (points.length >= 2) {
      const midpointIndex = Math.floor((points.length - 1) / 2);
      const start = points[midpointIndex];
      const end = points[midpointIndex + 1] ?? start;
      return { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 - 6 };
    }
  }

  const bounds = normalizeBounds(object.bounds);
  if (object.kind === 'symbol') {
    return { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height + Math.max(12, object.style.fontSize ?? 11) };
  }
  return { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
}

function labelBounds(object: DrawingObject): DrawingBounds {
  const bounds = normalizeBounds(object.bounds);
  if (bounds.width > 0 || bounds.height > 0) {
    return bounds;
  }

  const point = object.points[0] ?? { x: 0, y: 0 };
  return { x: point.x, y: point.y, width: 80, height: 18 };
}

function normalizeBounds(bounds: DrawingBounds): DrawingBounds {
  const right = bounds.x + bounds.width;
  const bottom = bounds.y + bounds.height;
  const x = Math.min(finiteNumber(bounds.x), finiteNumber(right));
  const y = Math.min(finiteNumber(bounds.y), finiteNumber(bottom));
  return {
    x,
    y,
    width: Math.max(0, Math.max(finiteNumber(bounds.x), finiteNumber(right)) - x),
    height: Math.max(0, Math.max(finiteNumber(bounds.y), finiteNumber(bottom)) - y),
  };
}

function objectAriaLabel(object: DrawingObject): string {
  const label = object.label.trim() || object.id;
  return `${object.kind.replace(/_/g, ' ')} ${label}${object.locked ? ', locked' : ''}`;
}

function sourceFragmentImageUrl(object: DrawingObject, sourceImageBaseUrl: string | null): string | null {
  if (!sourceImageBaseUrl) {
    return null;
  }
  const metadata = object.metadata ?? {};
  const sourceFileId = metadata.sourceFileId;
  if (typeof sourceFileId !== 'string' || !sourceFileId.trim()) {
    return null;
  }
  const pageValue = metadata.page;
  const page = typeof pageValue === 'number' ? pageValue : Number(pageValue);
  if (!Number.isFinite(page) || page < 1) {
    return null;
  }
  return `${sourceImageBaseUrl}/${encodeURIComponent(sourceFileId)}/pages/${Math.floor(page)}/image?dpi=120`;
}

function connectorFallbackStroke(object: DrawingObject): string {
  const systemColor = object.metadata?.systemColor;
  if (typeof systemColor === 'string' && systemColor.trim()) {
    return systemColor;
  }
  return object.kind === 'connector' ? 'var(--rec-edge-signal)' : 'var(--rec-edge-pipe)';
}

function dashArray(dash: number[] | null | undefined): string | undefined {
  return dash && dash.length > 0 ? dash.join(' ') : undefined;
}

function safeOpacity(value: number | undefined, fallback: number): number {
  if (value === undefined || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(1, Math.max(0, value));
}

function finitePositive(value: number, fallback: number): number {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function fitLargeDrawingViewport(drawingWidth: number, drawingHeight: number, size: CanvasSize) {
  const padding = 48;
  const availableWidth = Math.max(1, size.width - padding * 2);
  const availableHeight = Math.max(1, size.height - padding * 2);
  const needsFit = drawingWidth > availableWidth || drawingHeight > availableHeight;
  if (!needsFit) {
    return null;
  }

  const zoom = Math.max(
    MIN_CANVAS_ZOOM,
    Math.min(1, availableWidth / drawingWidth, availableHeight / drawingHeight),
  );
  return {
    x: (size.width - drawingWidth * zoom) / 2,
    y: (size.height - drawingHeight * zoom) / 2,
    zoom,
  };
}

function finiteNumber(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

function capturePointer(target: SVGElement, pointerId: number): void {
  try {
    target.setPointerCapture(pointerId);
  } catch {
    // Pointer capture can fail in tests or if the pointer was already released.
  }
}

function releasePointerCapture(target: SVGElement, pointerId: number): void {
  try {
    target.releasePointerCapture(pointerId);
  } catch {
    // The drag is already over from the user's perspective.
  }
}
