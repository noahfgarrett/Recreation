import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type PointerEvent as ReactPointerEvent,
  type SetStateAction,
  type WheelEvent as ReactWheelEvent,
} from 'react';
import type { DrawingPoint } from '../../types';
import type { ViewportTransform } from './drawingGeometry';

export const MIN_CANVAS_ZOOM = 0.1;
export const MAX_CANVAS_ZOOM = 8;
export const DEFAULT_CANVAS_VIEWPORT: ViewportTransform = { x: 0, y: 0, zoom: 1 };

const WHEEL_ZOOM_SENSITIVITY = 0.001;

type CanvasElement = HTMLElement | SVGElement;
type CanvasPointerEvent = ReactPointerEvent<CanvasElement>;
type CanvasWheelEvent = ReactWheelEvent<CanvasElement>;
type WheelLike = {
  ctrlKey: boolean;
  metaKey: boolean;
  deltaY: number;
  clientX: number;
  clientY: number;
  currentTarget?: EventTarget | null;
  preventDefault: () => void;
};

interface PanState {
  pointerId: number;
  lastX: number;
  lastY: number;
}

export interface CanvasNavigationHandlers {
  onWheel: (event: CanvasWheelEvent) => void;
  onPointerDown: (event: CanvasPointerEvent) => void;
  onPointerMove: (event: CanvasPointerEvent) => void;
  onPointerUp: (event: CanvasPointerEvent) => void;
  onPointerCancel: (event: CanvasPointerEvent) => void;
}

export interface CanvasNavigationControls extends CanvasNavigationHandlers {
  viewport: ViewportTransform;
  setViewport: Dispatch<SetStateAction<ViewportTransform>>;
  resetViewport: () => void;
  isPanning: boolean;
  onNativeWheel: (event: WheelEvent, target?: CanvasElement | null) => void;
  navigationProps: CanvasNavigationHandlers;
}

export function zoomViewportAtPoint(
  viewport: ViewportTransform,
  screenPoint: DrawingPoint,
  nextZoom: number,
): ViewportTransform {
  const zoom = clampZoom(nextZoom);
  const currentZoom = clampZoom(viewport.zoom);
  const currentX = finiteNumber(viewport.x);
  const currentY = finiteNumber(viewport.y);
  const screenX = finiteNumber(screenPoint.x);
  const screenY = finiteNumber(screenPoint.y);
  const anchorWorldX = (screenX - currentX) / currentZoom;
  const anchorWorldY = (screenY - currentY) / currentZoom;

  return {
    x: screenX - anchorWorldX * zoom,
    y: screenY - anchorWorldY * zoom,
    zoom,
  };
}

export function panViewport(viewport: ViewportTransform, dx: number, dy: number): ViewportTransform {
  return {
    x: finiteNumber(viewport.x) + finiteNumber(dx),
    y: finiteNumber(viewport.y) + finiteNumber(dy),
    zoom: clampZoom(viewport.zoom),
  };
}

export function useCanvasNavigation(initial?: Partial<ViewportTransform>): CanvasNavigationControls {
  const initialViewport = useMemo(() => normalizeViewport(initial), [initial]);
  const [viewport, setViewportState] = useState<ViewportTransform>(initialViewport);
  const [isPanning, setIsPanning] = useState(false);
  const panState = useRef<PanState | null>(null);

  const setViewport = useCallback<Dispatch<SetStateAction<ViewportTransform>>>((next) => {
    setViewportState((current) => normalizeViewport(typeof next === 'function' ? next(current) : next));
  }, []);

  const resetViewport = useCallback(() => {
    setViewport(initialViewport);
  }, [initialViewport, setViewport]);

  const applyWheelZoom = useCallback(
    (event: WheelLike, target?: CanvasElement | null) => {
      if (!event.ctrlKey && !event.metaKey) {
        return;
      }

      event.preventDefault();
      const screenPoint = screenPointForEvent(event, target);
      const deltaY = finiteNumber(event.deltaY);
      const zoomFactor = Math.exp(-deltaY * WHEEL_ZOOM_SENSITIVITY);
      setViewport((current) => zoomViewportAtPoint(current, screenPoint, current.zoom * zoomFactor));
    },
    [setViewport],
  );

  const onWheel = useCallback(
    (event: CanvasWheelEvent) => {
      applyWheelZoom(event, event.currentTarget);
    },
    [applyWheelZoom],
  );

  const onNativeWheel = useCallback(
    (event: WheelEvent, target?: CanvasElement | null) => {
      applyWheelZoom(event, target ?? (event.currentTarget as CanvasElement | null));
    },
    [applyWheelZoom],
  );

  const onPointerDown = useCallback((event: CanvasPointerEvent) => {
    if (event.button !== 1) {
      return;
    }

    event.preventDefault();
    panState.current = {
      pointerId: event.pointerId,
      lastX: finiteNumber(event.clientX),
      lastY: finiteNumber(event.clientY),
    };
    setIsPanning(true);
    safelyCallPointerCapture(event.currentTarget, 'setPointerCapture', event.pointerId);
  }, []);

  const onPointerMove = useCallback(
    (event: CanvasPointerEvent) => {
      const currentPan = panState.current;
      if (!currentPan || currentPan.pointerId !== event.pointerId) {
        return;
      }

      event.preventDefault();
      const clientX = finiteNumber(event.clientX);
      const clientY = finiteNumber(event.clientY);
      const dx = clientX - currentPan.lastX;
      const dy = clientY - currentPan.lastY;
      panState.current = { ...currentPan, lastX: clientX, lastY: clientY };
      setViewport((current) => panViewport(current, dx, dy));
    },
    [setViewport],
  );

  const stopPanning = useCallback((event: CanvasPointerEvent) => {
    const currentPan = panState.current;
    if (!currentPan || currentPan.pointerId !== event.pointerId) {
      return;
    }

    safelyCallPointerCapture(event.currentTarget, 'releasePointerCapture', event.pointerId);
    panState.current = null;
    setIsPanning(false);
  }, []);

  const navigationProps = useMemo(
    () => ({
      onWheel,
      onPointerDown,
      onPointerMove,
      onPointerUp: stopPanning,
      onPointerCancel: stopPanning,
    }),
    [onPointerDown, onPointerMove, onWheel, stopPanning],
  );

  return {
    viewport,
    setViewport,
    resetViewport,
    isPanning,
    onNativeWheel,
    ...navigationProps,
    navigationProps,
  };
}

function normalizeViewport(viewport: Partial<ViewportTransform> | undefined): ViewportTransform {
  return {
    x: finiteNumber(viewport?.x ?? DEFAULT_CANVAS_VIEWPORT.x),
    y: finiteNumber(viewport?.y ?? DEFAULT_CANVAS_VIEWPORT.y),
    zoom: clampZoom(viewport?.zoom ?? DEFAULT_CANVAS_VIEWPORT.zoom),
  };
}

function screenPointForEvent(event: WheelLike, target?: CanvasElement | null): DrawingPoint {
  const fallbackTarget = event.currentTarget instanceof Element ? event.currentTarget : null;
  const rect = (target ?? fallbackTarget)?.getBoundingClientRect?.();
  return {
    x: finiteNumber(event.clientX) - finiteNumber(rect?.left ?? 0),
    y: finiteNumber(event.clientY) - finiteNumber(rect?.top ?? 0),
  };
}

function safelyCallPointerCapture(
  target: CanvasElement,
  method: 'setPointerCapture' | 'releasePointerCapture',
  pointerId: number,
): void {
  try {
    target[method]?.(pointerId);
  } catch {
    // Browsers can throw when capture has already been lost; panning should still stop cleanly.
  }
}

function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) {
    return 1;
  }
  return Math.min(MAX_CANVAS_ZOOM, Math.max(MIN_CANVAS_ZOOM, zoom));
}

function finiteNumber(value: number): number {
  return Number.isFinite(value) ? value : 0;
}
