import { describe, expect, test } from 'vitest';
import {
  boundsForPoints,
  hitTestBounds,
  routeOrthogonal,
  screenToWorld,
  worldToScreen,
} from './drawingGeometry';

describe('drawingGeometry', () => {
  test('converts between world and screen coordinates with pan and zoom', () => {
    const viewport = { x: 100, y: -50, zoom: 2 };
    const worldPoint = { x: 10, y: 20 };

    const screenPoint = worldToScreen(worldPoint, viewport);

    expect(screenPoint).toEqual({ x: 120, y: -10 });
    expect(screenToWorld(screenPoint, viewport)).toEqual(worldPoint);
  });

  test('routes orthogonally through midpoint x and removes duplicate adjacent points', () => {
    expect(routeOrthogonal({ x: 0, y: 0 }, { x: 10, y: 20 })).toEqual([
      { x: 0, y: 0 },
      { x: 5, y: 0 },
      { x: 5, y: 20 },
      { x: 10, y: 20 },
    ]);

    expect(routeOrthogonal({ x: 0, y: 0 }, { x: 10, y: 0 })).toEqual([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
    ]);
  });

  test('returns padded bounds for points', () => {
    expect(
      boundsForPoints(
        [
          { x: -5, y: 10 },
          { x: 8, y: 3 },
          { x: 0, y: 15 },
        ],
        2,
      ),
    ).toEqual({ x: -7, y: 1, width: 17, height: 16 });
  });

  test('returns zero bounds for empty points', () => {
    expect(boundsForPoints([])).toEqual({ x: 0, y: 0, width: 0, height: 0 });
  });

  test('hit tests bounds with optional padding', () => {
    const bounds = { x: 10, y: 20, width: 30, height: 40 };

    expect(hitTestBounds({ x: 10, y: 20 }, bounds)).toBe(true);
    expect(hitTestBounds({ x: 41, y: 20 }, bounds)).toBe(false);
    expect(hitTestBounds({ x: 41, y: 20 }, bounds, 1)).toBe(true);
  });
});
