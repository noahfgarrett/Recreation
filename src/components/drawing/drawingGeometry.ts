import type { DrawingBounds, DrawingPoint } from '../../types';

export type Point = DrawingPoint;
export type Bounds = DrawingBounds;

export interface ViewportTransform {
  x: number;
  y: number;
  zoom: number;
}

const EMPTY_BOUNDS: Bounds = { x: 0, y: 0, width: 0, height: 0 };

export function worldToScreen(point: Point, viewport: ViewportTransform): Point {
  const zoom = validZoom(viewport.zoom);
  return {
    x: point.x * zoom + viewport.x,
    y: point.y * zoom + viewport.y,
  };
}

export function screenToWorld(point: Point, viewport: ViewportTransform): Point {
  const zoom = validZoom(viewport.zoom);
  return {
    x: (point.x - viewport.x) / zoom,
    y: (point.y - viewport.y) / zoom,
  };
}

export function routeOrthogonal(start: Point, end: Point): Point[] {
  const midpointX = (start.x + end.x) / 2;
  const route = [
    { x: start.x, y: start.y },
    { x: midpointX, y: start.y },
    { x: midpointX, y: end.y },
    { x: end.x, y: end.y },
  ];

  return simplifyColinearPoints(dedupeAdjacentPoints(route));
}

export function boundsForPoints(points: Point[], padding = 0): Bounds {
  const finitePoints = points.filter(isFinitePoint);
  if (finitePoints.length === 0) {
    return { ...EMPTY_BOUNDS };
  }

  const pad = normalizedPadding(padding);
  let minX = finitePoints[0].x;
  let minY = finitePoints[0].y;
  let maxX = finitePoints[0].x;
  let maxY = finitePoints[0].y;

  for (const point of finitePoints.slice(1)) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }

  return {
    x: minX - pad,
    y: minY - pad,
    width: maxX - minX + pad * 2,
    height: maxY - minY + pad * 2,
  };
}

export function translateBounds(bounds: Bounds, delta: Point): Bounds {
  return {
    ...bounds,
    x: bounds.x + delta.x,
    y: bounds.y + delta.y,
  };
}

export function translatePoints(points: Point[], delta: Point): Point[] {
  return points.map((point) => ({
    x: point.x + delta.x,
    y: point.y + delta.y,
  }));
}

export function hitTestBounds(point: Point, bounds: Bounds, padding = 0): boolean {
  const expanded = expandBounds(bounds, padding);
  const left = Math.min(expanded.x, expanded.x + expanded.width);
  const right = Math.max(expanded.x, expanded.x + expanded.width);
  const top = Math.min(expanded.y, expanded.y + expanded.height);
  const bottom = Math.max(expanded.y, expanded.y + expanded.height);

  return point.x >= left && point.x <= right && point.y >= top && point.y <= bottom;
}

export function expandBounds(bounds: Bounds, padding: number): Bounds {
  const pad = normalizedPadding(padding);
  return {
    x: bounds.x - pad,
    y: bounds.y - pad,
    width: bounds.width + pad * 2,
    height: bounds.height + pad * 2,
  };
}

function dedupeAdjacentPoints(points: Point[]): Point[] {
  return points.reduce<Point[]>((deduped, point) => {
    const previous = deduped[deduped.length - 1];
    if (!previous || previous.x !== point.x || previous.y !== point.y) {
      deduped.push(point);
    }
    return deduped;
  }, []);
}

function simplifyColinearPoints(points: Point[]): Point[] {
  if (points.length <= 2) {
    return points;
  }

  const simplified: Point[] = [points[0]];
  for (let index = 1; index < points.length - 1; index += 1) {
    const previous = simplified[simplified.length - 1];
    const current = points[index];
    const next = points[index + 1];
    const isHorizontal = previous.y === current.y && current.y === next.y;
    const isVertical = previous.x === current.x && current.x === next.x;

    if (!isHorizontal && !isVertical) {
      simplified.push(current);
    }
  }

  const last = points[points.length - 1];
  const previous = simplified[simplified.length - 1];
  if (previous.x !== last.x || previous.y !== last.y) {
    simplified.push(last);
  }
  return simplified;
}

function isFinitePoint(point: Point): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

function normalizedPadding(padding: number): number {
  return Number.isFinite(padding) ? Math.max(0, padding) : 0;
}

function validZoom(zoom: number): number {
  if (!Number.isFinite(zoom) || zoom === 0) {
    throw new RangeError('Viewport zoom must be a non-zero finite number.');
  }
  return zoom;
}
