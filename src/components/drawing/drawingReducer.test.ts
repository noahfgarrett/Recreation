import { describe, expect, test } from 'vitest';
import type { DrawingDocument, DrawingObject, DrawingStyle } from '../../types';
import { drawingReducer } from './drawingReducer';

const baseStyle: DrawingStyle = {
  stroke: '#111827',
  fill: 'transparent',
  strokeWidth: 2,
  opacity: 1,
};

const pipe: DrawingObject = {
  id: 'pipe-1',
  kind: 'pipe',
  label: 'Line 100',
  points: [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 15 },
  ],
  bounds: { x: 0, y: 0, width: 10, height: 15 },
  style: baseStyle,
  sourceEvidenceIds: ['ev-1'],
};

const label: DrawingObject = {
  id: 'label-1',
  kind: 'label',
  label: 'Old label',
  points: [],
  bounds: { x: 30, y: 5, width: 20, height: 8 },
  style: { ...baseStyle, strokeWidth: 1, fontSize: 12 },
  sourceEvidenceIds: [],
};

function createDocument(): DrawingDocument {
  return {
    id: 'drawing-1',
    projectId: 'project-1',
    name: 'Test drawing',
    width: 100,
    height: 80,
    objects: [pipe, label],
    sourcePages: [],
    styles: { default: baseStyle },
    visualQa: {},
  };
}

describe('drawingReducer', () => {
  test('moves object points and bounds without mutating the original document', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'moveObject',
      objectId: 'pipe-1',
      delta: { x: 5, y: -3 },
    });

    expect(next).not.toBe(document);
    expect(next.id).toBe(document.id);
    expect(next.projectId).toBe(document.projectId);
    expect(next.objects[0]).not.toBe(document.objects[0]);
    expect(next.objects[1]).toBe(document.objects[1]);
    expect(next.objects[0].points).toEqual([
      { x: 5, y: -3 },
      { x: 15, y: -3 },
      { x: 15, y: 12 },
    ]);
    expect(next.objects[0].bounds).toEqual({ x: 5, y: -3, width: 10, height: 15 });
    expect(document.objects[0].points).toEqual(pipe.points);
    expect(document.objects[0].bounds).toEqual(pipe.bounds);
  });

  test('updates a label and preserves untouched object references', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'updateLabel',
      id: 'label-1',
      label: 'New label',
    });

    expect(next.objects[0]).toBe(document.objects[0]);
    expect(next.objects[1]).not.toBe(document.objects[1]);
    expect(next.objects[1].label).toBe('New label');
  });

  test('merges object style updates', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'updateObjectStyle',
      objectId: 'pipe-1',
      style: { stroke: '#ef4444', dash: [4, 2] },
    });

    expect(next.objects[0].style).toEqual({
      ...baseStyle,
      stroke: '#ef4444',
      dash: [4, 2],
    });
    expect(next.objects[1]).toBe(document.objects[1]);
  });

  test('moves connector endpoints attached to a moved symbol', () => {
    const symbol: DrawingObject = {
      id: 'pump-1',
      kind: 'symbol',
      label: 'Pump',
      points: [
        { x: 80, y: 40 },
        { x: 120, y: 70 },
      ],
      bounds: { x: 80, y: 40, width: 40, height: 30 },
      style: baseStyle,
      sourceEvidenceIds: [],
    };
    const connectedPipe: DrawingObject = {
      ...pipe,
      id: 'pipe-attached',
      points: [
        { x: 10, y: 55 },
        { x: 80, y: 55 },
      ],
      bounds: { x: 10, y: 55, width: 70, height: 0 },
    };
    const document = { ...createDocument(), objects: [connectedPipe, symbol] };

    const next = drawingReducer(document, {
      type: 'moveObject',
      id: 'pump-1',
      dx: 20,
      dy: -10,
    });

    expect(next.objects[1].bounds).toEqual({ x: 100, y: 30, width: 40, height: 30 });
    expect(next.objects[0].points).toEqual([
      { x: 10, y: 55 },
      { x: 100, y: 45 },
    ]);
  });

  test('uses explicit connector metadata when moving connected objects', () => {
    const symbol: DrawingObject = {
      id: 'node-a',
      kind: 'symbol',
      label: 'Node A',
      points: [
        { x: 50, y: 50 },
        { x: 90, y: 80 },
      ],
      bounds: { x: 50, y: 50, width: 40, height: 30 },
      style: baseStyle,
      sourceEvidenceIds: [],
    };
    const connector: DrawingObject = {
      ...pipe,
      id: 'connector-1',
      kind: 'connector',
      points: [
        { x: 200, y: 200 },
        { x: 260, y: 200 },
      ],
      bounds: { x: 200, y: 200, width: 60, height: 0 },
      metadata: { startObjectId: 'node-a' },
    };
    const document = { ...createDocument(), objects: [connector, symbol] };

    const next = drawingReducer(document, {
      type: 'moveObject',
      id: 'node-a',
      dx: -15,
      dy: 25,
    });

    expect(next.objects[0].points).toEqual([
      { x: 185, y: 225 },
      { x: 260, y: 200 },
    ]);
  });

  test('does not implicitly attach connector endpoints to large regions', () => {
    const region: DrawingObject = {
      id: 'plant-zone',
      kind: 'region',
      label: 'Plant zone',
      points: [
        { x: 0, y: 0 },
        { x: 300, y: 0 },
        { x: 300, y: 240 },
        { x: 0, y: 240 },
      ],
      bounds: { x: 0, y: 0, width: 300, height: 240 },
      style: baseStyle,
      sourceEvidenceIds: [],
    };
    const connector: DrawingObject = {
      ...pipe,
      id: 'pipe-inside-region',
      points: [
        { x: 40, y: 80 },
        { x: 240, y: 80 },
      ],
      bounds: { x: 40, y: 80, width: 200, height: 0 },
    };
    const document = { ...createDocument(), objects: [region, connector] };

    const next = drawingReducer(document, {
      type: 'moveObject',
      id: 'plant-zone',
      dx: 40,
      dy: 20,
    });

    expect(next.objects[0].bounds).toEqual({ x: 40, y: 20, width: 300, height: 240 });
    expect(next.objects[1].points).toEqual(connector.points);
  });

  test('adds an editable dogleg bend to connector lines', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'addConnectorBend',
      id: 'pipe-1',
    });

    expect(next.objects[0].points.length).toBeGreaterThan(document.objects[0].points.length);
    expect(next.objects[0].bounds.width).toBeGreaterThan(0);
    expect(next.objects[0].bounds.height).toBeGreaterThan(0);
  });

  test('adds generic drawing objects and updates object metadata', () => {
    const document = createDocument();
    const textBox: DrawingObject = {
      id: 'text-1',
      kind: 'label',
      label: 'Note',
      points: [
        { x: 5, y: 5 },
        { x: 40, y: 18 },
      ],
      bounds: { x: 5, y: 5, width: 35, height: 13 },
      style: { ...baseStyle, fontSize: 14 },
      sourceEvidenceIds: [],
      metadata: { textBox: true },
    };

    const withText = drawingReducer(document, { type: 'addObject', object: textBox });
    const updated = drawingReducer(withText, {
      type: 'updateObjectMetadata',
      id: 'text-1',
      metadata: { textAlign: 'center', fontStyle: 'italic' },
    });

    expect(withText.objects.at(-1)).toEqual(textBox);
    expect(updated.objects.at(-1)?.metadata).toMatchObject({
      textBox: true,
      textAlign: 'center',
      fontStyle: 'italic',
    });
  });

  test('updates object points and recomputes bounds', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'updateObjectPoints',
      id: 'pipe-1',
      points: [
        { x: -2, y: 5 },
        { x: 6, y: 9 },
      ],
    });

    expect(next.objects[0].points).toEqual([
      { x: -2, y: 5 },
      { x: 6, y: 9 },
    ]);
    expect(next.objects[0].bounds).toEqual({ x: -2, y: 5, width: 8, height: 4 });
    expect(next.objects[1]).toBe(document.objects[1]);
  });

  test('updates rect-like object bounds by normalizing bounds and replacing points with rectangle corners', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'updateObjectBounds',
      id: 'label-1',
      bounds: { x: 50, y: 30, width: -20, height: -10 },
    });

    expect(next.objects[1].bounds).toEqual({ x: 30, y: 20, width: 20, height: 10 });
    expect(next.objects[1].points).toEqual([
      { x: 30, y: 20 },
      { x: 50, y: 20 },
      { x: 50, y: 30 },
      { x: 30, y: 30 },
    ]);
  });

  test('does not update pipe bounds directly', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'updateObjectBounds',
      id: 'pipe-1',
      bounds: { x: 5, y: 5, width: 40, height: 20 },
    });

    expect(next).toBe(document);
  });

  test('locked objects ignore mutating actions unless forced', () => {
    const lockedFragment: DrawingObject = {
      id: 'source-1',
      kind: 'source_fragment',
      label: 'Locked fragment',
      points: [
        { x: 1, y: 2 },
        { x: 9, y: 6 },
      ],
      bounds: { x: 1, y: 2, width: 8, height: 4 },
      style: baseStyle,
      sourceEvidenceIds: ['ev-locked'],
      locked: true,
    };
    const document = { ...createDocument(), objects: [lockedFragment] };

    expect(drawingReducer(document, { type: 'moveObject', id: 'source-1', delta: { x: 1, y: 1 } })).toBe(document);
    expect(drawingReducer(document, { type: 'updateLabel', id: 'source-1', label: 'Changed' })).toBe(document);
    expect(drawingReducer(document, { type: 'updateObjectStyle', id: 'source-1', style: { stroke: '#ef4444' } })).toBe(document);
    expect(drawingReducer(document, { type: 'updateObjectBounds', id: 'source-1', bounds: { x: 0, y: 0, width: 5, height: 5 } })).toBe(document);
    expect(drawingReducer(document, { type: 'updateObjectPoints', id: 'source-1', points: [{ x: 0, y: 0 }] })).toBe(document);
    expect(drawingReducer(document, { type: 'deleteObject', id: 'source-1' })).toBe(document);

    const forced = drawingReducer(document, {
      type: 'updateLabel',
      id: 'source-1',
      label: 'Forced label',
      force: true,
    });

    expect(forced).not.toBe(document);
    expect(forced.objects[0].label).toBe('Forced label');
  });

  test('ignores non-finite move deltas and point updates', () => {
    const document = createDocument();

    expect(
      drawingReducer(document, {
        type: 'moveObject',
        id: 'pipe-1',
        delta: { x: Number.NaN, y: 1 },
      }),
    ).toBe(document);
    expect(
      drawingReducer(document, {
        type: 'updateObjectPoints',
        id: 'pipe-1',
        points: [
          { x: 1, y: 2 },
          { x: Infinity, y: 4 },
        ],
      }),
    ).toBe(document);
  });

  test('ignores non-finite bounds', () => {
    const document = createDocument();

    const next = drawingReducer(document, {
      type: 'updateObjectBounds',
      id: 'label-1',
      bounds: { x: 0, y: Number.NaN, width: 10, height: 10 },
    });

    expect(next).toBe(document);
  });

  test('missing target preserves the original document reference', () => {
    const document = createDocument();

    expect(drawingReducer(document, { type: 'moveObject', id: 'missing', delta: { x: 1, y: 1 } })).toBe(document);
    expect(drawingReducer(document, { type: 'updateLabel', id: 'missing', label: 'Nope' })).toBe(document);
    expect(drawingReducer(document, { type: 'updateObjectStyle', id: 'missing', style: { stroke: '#ef4444' } })).toBe(document);
    expect(drawingReducer(document, { type: 'updateObjectBounds', id: 'missing', bounds: { x: 0, y: 0, width: 1, height: 1 } })).toBe(document);
    expect(drawingReducer(document, { type: 'updateObjectPoints', id: 'missing', points: [{ x: 0, y: 0 }] })).toBe(document);
    expect(drawingReducer(document, { type: 'deleteObject', id: 'missing' })).toBe(document);
  });

  test('adds and deletes a region object', () => {
    const document = createDocument();
    const region: DrawingObject = {
      id: 'region-1',
      kind: 'region',
      label: 'Review area',
      points: [
        { x: 2, y: 3 },
        { x: 12, y: 9 },
      ],
      bounds: { x: 2, y: 3, width: 10, height: 6 },
      style: { ...baseStyle, fill: '#fee2e2', opacity: 0.5 },
      sourceEvidenceIds: [],
    };

    const withRegion = drawingReducer(document, { type: 'addRegion', object: region });
    const withoutRegion = drawingReducer(withRegion, { type: 'deleteObject', id: 'region-1' });

    expect(withRegion.objects).toEqual([...document.objects, region]);
    expect(withRegion.objects[0]).toBe(document.objects[0]);
    expect(withRegion.objects[1]).toBe(document.objects[1]);
    expect(withoutRegion.objects).toEqual(document.objects);
  });
});
