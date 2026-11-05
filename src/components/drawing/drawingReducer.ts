import type { DrawingBounds, DrawingDocument, DrawingObject, DrawingPoint, DrawingStyle } from '../../types';
import { boundsForPoints, hitTestBounds, translateBounds, translatePoints } from './drawingGeometry';

type TargetedAction = {
  id?: string;
  objectId?: string;
  force?: boolean;
};

export type DrawingAction =
  | (TargetedAction & {
      type: 'moveObject';
      delta?: Partial<DrawingPoint>;
      dx?: number;
      dy?: number;
    })
  | (TargetedAction & {
      type: 'updateLabel';
      label: string;
    })
  | (TargetedAction & {
      type: 'updateObjectStyle';
      style: Partial<DrawingStyle>;
    })
  | (TargetedAction & {
      type: 'updateObjectMetadata';
      metadata: Record<string, unknown>;
    })
  | {
      type: 'addObject';
      object: DrawingObject;
    }
  | {
      type: 'addRegion';
      object?: DrawingObject;
      region?: DrawingObject;
      id?: string;
      label?: string;
      points?: DrawingPoint[];
      bounds?: DrawingBounds;
      style?: Partial<DrawingStyle>;
      sourceEvidenceIds?: string[];
      locked?: boolean;
      groupId?: string | null;
      metadata?: Record<string, unknown>;
    }
  | (TargetedAction & {
      type: 'updateObjectBounds';
      bounds: DrawingBounds;
    })
  | (TargetedAction & {
      type: 'updateObjectPoints';
      points: DrawingPoint[];
    })
  | (TargetedAction & {
      type: 'deleteObject';
    })
  | (TargetedAction & {
      type: 'addConnectorBend';
    })
  | {
      type: 'setObjects';
      objects: DrawingObject[];
    };

const DEFAULT_REGION_STYLE: DrawingStyle = {
  stroke: '#2563eb',
  fill: 'rgba(37, 99, 235, 0.08)',
  strokeWidth: 1,
  opacity: 1,
};

export function drawingReducer(document: DrawingDocument, action: DrawingAction): DrawingDocument {
  switch (action.type) {
    case 'moveObject': {
      const delta = {
        x: action.delta?.x ?? action.dx ?? 0,
        y: action.delta?.y ?? action.dy ?? 0,
      };
      if (!isFinitePoint(delta) || (delta.x === 0 && delta.y === 0)) {
        return document;
      }

      return moveObjectWithConnections(document, action, delta);
    }

    case 'updateLabel':
      return updateObject(document, action, (object) => {
        if (object.label === action.label) {
          return object;
        }
        return { ...object, label: action.label };
      });

    case 'updateObjectStyle':
      return updateObject(document, action, (object) => {
        const nextStyle = { ...object.style, ...action.style };
        if (shallowEqual(object.style, nextStyle)) {
          return object;
        }
        return { ...object, style: nextStyle };
      });

    case 'updateObjectMetadata':
      return updateObject(document, action, (object) => {
        const nextMetadata = { ...(object.metadata ?? {}), ...action.metadata };
        for (const [key, value] of Object.entries(nextMetadata)) {
          if (value === undefined) {
            delete nextMetadata[key];
          }
        }
        if (shallowEqual(object.metadata ?? {}, nextMetadata)) {
          return object;
        }
        return { ...object, metadata: nextMetadata };
      });

    case 'addObject': {
      const object = validateNewObject(action.object);
      if (!object || document.objects.some((candidate) => candidate.id === object.id)) {
        return document;
      }
      return { ...document, objects: [...document.objects, object] };
    }

    case 'addRegion': {
      const region = regionFromAction(action);
      if (!region || document.objects.some((object) => object.id === region.id)) {
        return document;
      }
      return { ...document, objects: [...document.objects, region] };
    }

    case 'updateObjectBounds':
      return updateObject(document, action, (object) => {
        if (!canUpdateBounds(object)) {
          return object;
        }

        const bounds = normalizeBounds(action.bounds);
        if (!bounds) {
          return object;
        }

        const points = rectanglePointsForBounds(bounds);
        if (boundsEqual(object.bounds, bounds) && pointsEqual(object.points, points)) {
          return object;
        }
        return { ...object, bounds, points };
      });

    case 'updateObjectPoints':
      return updateObject(document, action, (object) => {
        if (!action.points.every(isFinitePoint)) {
          return object;
        }

        const points = action.points.map(copyPoint);
        const bounds = boundsForPoints(points);
        if (pointsEqual(object.points, points) && boundsEqual(object.bounds, bounds)) {
          return object;
        }
        return { ...object, points, bounds };
      });

    case 'deleteObject': {
      const id = targetId(action);
      const object = document.objects.find((candidate) => candidate.id === id);
      if (!id || !object || isLocked(object, action)) {
        return document;
      }
      return { ...document, objects: document.objects.filter((object) => object.id !== id) };
    }

    case 'addConnectorBend':
      return updateObject(document, action, (object) => {
        if (!isConnectorObject(object) || object.points.length < 2) {
          return object;
        }
        const points = addDoglegBend(object.points);
        if (pointsEqual(object.points, points)) {
          return object;
        }
        return { ...object, points, bounds: boundsForPoints(points) };
      });

    case 'setObjects':
      if (sameObjects(document.objects, action.objects)) {
        return document;
      }
      return { ...document, objects: action.objects };
  }
}

function moveObjectWithConnections(
  document: DrawingDocument,
  action: TargetedAction,
  delta: DrawingPoint,
): DrawingDocument {
  const objectId = targetId(action);
  if (!objectId) {
    return document;
  }

  const target = document.objects.find((object) => object.id === objectId);
  if (!target || isLocked(target, action)) {
    return document;
  }

  const movedTarget = {
    ...target,
    points: translatePoints(target.points, delta),
    bounds: translateBounds(target.bounds, delta),
  };

  let changed = false;
  const objects = document.objects.map((object) => {
    if (object.id === objectId) {
      changed = true;
      return movedTarget;
    }

    const movedConnector = moveAttachedConnectorEndpoint(object, target, objectId, delta);
    if (movedConnector !== object) {
      changed = true;
    }
    return movedConnector;
  });

  return changed ? { ...document, objects } : document;
}

function updateObject(
  document: DrawingDocument,
  action: TargetedAction,
  update: (object: DrawingObject) => DrawingObject,
): DrawingDocument {
  const objectId = targetId(action);
  if (!objectId) {
    return document;
  }

  const index = document.objects.findIndex((object) => object.id === objectId);
  if (index === -1) {
    return document;
  }

  if (isLocked(document.objects[index], action)) {
    return document;
  }

  const nextObject = update(document.objects[index]);
  if (nextObject === document.objects[index]) {
    return document;
  }

  const objects = document.objects.slice();
  objects[index] = nextObject;
  return { ...document, objects };
}

function validateNewObject(object: DrawingObject): DrawingObject | null {
  if (!object.id || !object.points.every(isFinitePoint)) {
    return null;
  }

  const bounds = normalizeBounds(object.bounds);
  if (!bounds) {
    return null;
  }

  return {
    ...object,
    points: object.points.map(copyPoint),
    bounds,
    sourceEvidenceIds: object.sourceEvidenceIds ?? [],
  };
}

function targetId(action: TargetedAction): string | undefined {
  return action.objectId ?? action.id;
}

function isLocked(object: DrawingObject, action: TargetedAction): boolean {
  return object.locked === true && action.force !== true;
}

function regionFromAction(action: Extract<DrawingAction, { type: 'addRegion' }>): DrawingObject | null {
  const providedRegion = action.object ?? action.region;
  if (providedRegion) {
    const bounds = normalizeBounds(providedRegion.bounds);
    if (!bounds || !providedRegion.points.every(isFinitePoint)) {
      return null;
    }
    return {
      ...providedRegion,
      kind: 'region',
      points: providedRegion.points.map(copyPoint),
      bounds,
    };
  }

  if (!action.id) {
    return null;
  }

  const points = action.points?.map(copyPoint) ?? pointsForBounds(action.bounds);
  if (!points.every(isFinitePoint)) {
    return null;
  }

  const bounds = action.bounds ? normalizeBounds(action.bounds) : boundsForPoints(points);
  if (!bounds) {
    return null;
  }

  const region: DrawingObject = {
    id: action.id,
    kind: 'region',
    label: action.label ?? '',
    points,
    bounds,
    style: { ...DEFAULT_REGION_STYLE, ...action.style },
    sourceEvidenceIds: action.sourceEvidenceIds ?? [],
  };

  if (action.locked !== undefined) {
    region.locked = action.locked;
  }
  if (action.groupId !== undefined) {
    region.groupId = action.groupId;
  }
  if (action.metadata !== undefined) {
    region.metadata = action.metadata;
  }

  return region;
}

function pointsForBounds(bounds: DrawingBounds | undefined): DrawingPoint[] {
  const normalized = bounds ? normalizeBounds(bounds) : null;
  if (!normalized) {
    return [];
  }
  return [
    { x: normalized.x, y: normalized.y },
    { x: normalized.x + normalized.width, y: normalized.y + normalized.height },
  ];
}

function canUpdateBounds(object: DrawingObject): boolean {
  return object.kind === 'label' || object.kind === 'region' || object.kind === 'source_fragment' || object.kind === 'symbol';
}

function moveAttachedConnectorEndpoint(
  object: DrawingObject,
  movedObject: DrawingObject,
  movedObjectId: string,
  delta: DrawingPoint,
): DrawingObject {
  if (!canHostConnections(movedObject) || !isConnectorObject(object) || object.points.length < 2) {
    return object;
  }

  const points = object.points.map(copyPoint);
  let changed = false;
  const lastIndex = points.length - 1;

  if (endpointIsAttached(object, 'start', movedObject, movedObjectId)) {
    points[0] = { x: points[0].x + delta.x, y: points[0].y + delta.y };
    changed = true;
  }

  if (endpointIsAttached(object, 'end', movedObject, movedObjectId)) {
    points[lastIndex] = { x: points[lastIndex].x + delta.x, y: points[lastIndex].y + delta.y };
    changed = true;
  }

  if (!changed) {
    return object;
  }

  return {
    ...object,
    points,
    bounds: boundsForPoints(points),
  };
}

function canHostConnections(object: DrawingObject): boolean {
  return object.kind === 'symbol' || object.kind === 'label';
}

function isConnectorObject(object: DrawingObject): boolean {
  return object.kind === 'pipe' || object.kind === 'connector';
}

function endpointIsAttached(
  connector: DrawingObject,
  endpoint: 'start' | 'end',
  movedObject: DrawingObject,
  movedObjectId: string,
): boolean {
  const metadataKey = endpoint === 'start' ? 'startObjectId' : 'endObjectId';
  if (connector.metadata?.[metadataKey] === movedObjectId) {
    return true;
  }

  const point = endpoint === 'start' ? connector.points[0] : connector.points[connector.points.length - 1];
  return point ? hitTestBounds(point, movedObject.bounds, 18) : false;
}

function addDoglegBend(points: DrawingPoint[]): DrawingPoint[] {
  const copied = points.map(copyPoint);
  const segmentIndex = longestSegmentIndex(copied);
  if (segmentIndex === -1) {
    return copied;
  }

  const start = copied[segmentIndex];
  const end = copied[segmentIndex + 1];
  const offset = chooseDoglegOffset(copied, start, end);
  const horizontal = Math.abs(end.x - start.x) >= Math.abs(end.y - start.y);
  const additions = horizontal
    ? [
        { x: (start.x + end.x) / 2, y: start.y },
        { x: (start.x + end.x) / 2, y: start.y + offset },
        { x: end.x, y: start.y + offset },
      ]
    : [
        { x: start.x, y: (start.y + end.y) / 2 },
        { x: start.x + offset, y: (start.y + end.y) / 2 },
        { x: start.x + offset, y: end.y },
      ];

  return dedupeAdjacentPoints([...copied.slice(0, segmentIndex + 1), ...additions, ...copied.slice(segmentIndex + 1)]);
}

function longestSegmentIndex(points: DrawingPoint[]): number {
  let longest = -1;
  let longestIndex = -1;
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const length = Math.hypot(end.x - start.x, end.y - start.y);
    if (length > longest) {
      longest = length;
      longestIndex = index;
    }
  }
  return longestIndex;
}

function chooseDoglegOffset(points: DrawingPoint[], start: DrawingPoint, end: DrawingPoint): number {
  const horizontal = Math.abs(end.x - start.x) >= Math.abs(end.y - start.y);
  const midpoint = horizontal ? (start.y + end.y) / 2 : (start.x + end.x) / 2;
  const occupied = points.some((point) => Math.abs((horizontal ? point.y : point.x) - (midpoint + 56)) < 20);
  return occupied ? -56 : 56;
}

function dedupeAdjacentPoints(points: DrawingPoint[]): DrawingPoint[] {
  return points.reduce<DrawingPoint[]>((deduped, point) => {
    const previous = deduped[deduped.length - 1];
    if (!previous || previous.x !== point.x || previous.y !== point.y) {
      deduped.push(point);
    }
    return deduped;
  }, []);
}

function rectanglePointsForBounds(bounds: DrawingBounds): DrawingPoint[] {
  return [
    { x: bounds.x, y: bounds.y },
    { x: bounds.x + bounds.width, y: bounds.y },
    { x: bounds.x + bounds.width, y: bounds.y + bounds.height },
    { x: bounds.x, y: bounds.y + bounds.height },
  ];
}

function normalizeBounds(bounds: DrawingBounds): DrawingBounds | null {
  if (
    !Number.isFinite(bounds.x) ||
    !Number.isFinite(bounds.y) ||
    !Number.isFinite(bounds.width) ||
    !Number.isFinite(bounds.height)
  ) {
    return null;
  }

  const right = bounds.x + bounds.width;
  const bottom = bounds.y + bounds.height;
  if (!Number.isFinite(right) || !Number.isFinite(bottom)) {
    return null;
  }

  const x = Math.min(bounds.x, right);
  const y = Math.min(bounds.y, bottom);
  return {
    x,
    y,
    width: Math.max(bounds.x, right) - x,
    height: Math.max(bounds.y, bottom) - y,
  };
}

function copyPoint(point: DrawingPoint): DrawingPoint {
  return { x: point.x, y: point.y };
}

function isFinitePoint(point: DrawingPoint): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

function boundsEqual(a: DrawingBounds, b: DrawingBounds): boolean {
  return a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;
}

function pointsEqual(a: DrawingPoint[], b: DrawingPoint[]): boolean {
  return a.length === b.length && a.every((point, index) => point.x === b[index].x && point.y === b[index].y);
}

function sameObjects(a: DrawingObject[], b: DrawingObject[]): boolean {
  return a.length === b.length && a.every((object, index) => object === b[index]);
}

function shallowEqual<T extends object>(a: T, b: T): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    const left = a[key as keyof T];
    const right = b[key as keyof T];
    if (Array.isArray(left) && Array.isArray(right)) {
      if (left.length !== right.length || left.some((value, index) => value !== right[index])) {
        return false;
      }
    } else if (left !== right) {
      return false;
    }
  }
  return true;
}
