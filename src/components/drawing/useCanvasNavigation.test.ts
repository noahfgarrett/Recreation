import type { WheelEvent as ReactWheelEvent } from 'react';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import { screenToWorld } from './drawingGeometry';
import {
  MAX_CANVAS_ZOOM,
  MIN_CANVAS_ZOOM,
  panViewport,
  useCanvasNavigation,
  zoomViewportAtPoint,
} from './useCanvasNavigation';

describe('canvas navigation', () => {
  test('zooms around the cursor anchor', () => {
    const viewport = { x: 100, y: -50, zoom: 2 };
    const anchor = { x: 140, y: 10 };

    const before = screenToWorld(anchor, viewport);
    const next = zoomViewportAtPoint(viewport, anchor, 4);

    expect(next).toEqual({ x: 60, y: -110, zoom: 4 });
    expect(screenToWorld(anchor, next)).toEqual(before);
  });

  test('pans by a screen-space delta', () => {
    expect(panViewport({ x: 12, y: -4, zoom: 2 }, 15, -8)).toEqual({
      x: 27,
      y: -12,
      zoom: 2,
    });
  });

  test('clamps zoom to the canvas navigation range', () => {
    expect(zoomViewportAtPoint({ x: 0, y: 0, zoom: 1 }, { x: 10, y: 10 }, 0.001).zoom).toBe(MIN_CANVAS_ZOOM);
    expect(zoomViewportAtPoint({ x: 0, y: 0, zoom: 1 }, { x: 10, y: 10 }, 200).zoom).toBe(MAX_CANVAS_ZOOM);
  });

  test('returns a finite viewport when given non-finite values', () => {
    const next = zoomViewportAtPoint(
      { x: Number.NaN, y: Number.POSITIVE_INFINITY, zoom: Number.NaN },
      { x: Number.NaN, y: Number.NEGATIVE_INFINITY },
      Number.POSITIVE_INFINITY,
    );

    expect(Number.isFinite(next.x)).toBe(true);
    expect(Number.isFinite(next.y)).toBe(true);
    expect(Number.isFinite(next.zoom)).toBe(true);
  });

  test('does not handle wheel events without a ctrl or meta modifier', () => {
    const preventDefault = vi.fn();
    const { result } = renderHook(() => useCanvasNavigation({ x: 0, y: 0, zoom: 1 }));

    act(() => {
      result.current.onWheel({
        ctrlKey: false,
        metaKey: false,
        deltaY: -120,
        clientX: 50,
        clientY: 50,
        preventDefault,
      } as unknown as ReactWheelEvent<HTMLElement>);
    });

    expect(preventDefault).not.toHaveBeenCalled();
    expect(result.current.viewport).toEqual({ x: 0, y: 0, zoom: 1 });
  });

  test('zooms and prevents default for modifier wheel events', () => {
    const preventDefault = vi.fn();
    const currentTarget = {
      getBoundingClientRect: () => ({ left: 10, top: 20 }),
    };
    const { result } = renderHook(() => useCanvasNavigation({ x: 0, y: 0, zoom: 1 }));

    act(() => {
      result.current.onWheel({
        ctrlKey: true,
        metaKey: false,
        deltaY: -120,
        clientX: 50,
        clientY: 50,
        currentTarget,
        preventDefault,
      } as unknown as ReactWheelEvent<HTMLElement>);
    });

    const worldUnderCursor = screenToWorld({ x: 40, y: 30 }, result.current.viewport);
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(result.current.viewport.zoom).toBeGreaterThan(1);
    expect(worldUnderCursor.x).toBeCloseTo(40);
    expect(worldUnderCursor.y).toBeCloseTo(30);
  });

  test('middle pointer dragging pans and tolerates failed capture release', () => {
    const currentTarget = {
      setPointerCapture: vi.fn(),
      releasePointerCapture: vi.fn(() => {
        throw new Error('capture already released');
      }),
    };
    const { result } = renderHook(() => useCanvasNavigation({ x: 0, y: 0, zoom: 1 }));

    act(() => {
      result.current.onPointerDown({
        button: 1,
        pointerId: 7,
        clientX: 20,
        clientY: 30,
        currentTarget,
        preventDefault: vi.fn(),
      } as unknown as React.PointerEvent<HTMLElement>);
    });
    expect(result.current.isPanning).toBe(true);

    act(() => {
      result.current.onPointerMove({
        pointerId: 7,
        clientX: 25,
        clientY: 17,
        currentTarget,
        preventDefault: vi.fn(),
      } as unknown as React.PointerEvent<HTMLElement>);
    });
    expect(result.current.viewport).toEqual({ x: 5, y: -13, zoom: 1 });

    act(() => {
      result.current.onPointerUp({
        pointerId: 7,
        currentTarget,
      } as unknown as React.PointerEvent<HTMLElement>);
    });

    expect(currentTarget.setPointerCapture).toHaveBeenCalledWith(7);
    expect(currentTarget.releasePointerCapture).toHaveBeenCalledWith(7);
    expect(result.current.isPanning).toBe(false);
  });
});
