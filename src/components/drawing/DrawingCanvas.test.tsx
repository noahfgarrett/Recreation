import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import type { DrawingDocument, DrawingObject, DrawingStyle } from '../../types';
import { DrawingCanvas, objectLayerIds } from './DrawingCanvas';

const baseStyle: DrawingStyle = {
  stroke: '#334155',
  fill: 'transparent',
  strokeWidth: 2,
  opacity: 1,
};

afterEach(() => cleanup());

const region: DrawingObject = {
  id: 'region-1',
  kind: 'region',
  label: 'Area 1',
  points: [
    { x: 10, y: 10 },
    { x: 80, y: 50 },
  ],
  bounds: { x: 10, y: 10, width: 70, height: 40 },
  style: baseStyle,
  sourceEvidenceIds: [],
};

function createDrawing(): DrawingDocument {
  return {
    id: 'drawing-1',
    projectId: 'project-1',
    name: 'Canvas test',
    width: 400,
    height: 240,
    objects: [region],
    sourcePages: [],
    styles: { default: baseStyle },
    visualQa: {},
  };
}

describe('DrawingCanvas', () => {
  test('pans on left drag in pan mode without moving objects', () => {
    const onSelectObject = vi.fn();
    const onMoveObject = vi.fn();
    render(
      <DrawingCanvas
        drawing={createDrawing()}
        selectedId={null}
        mode="pan"
        onSelectObject={onSelectObject}
        onMoveObject={onMoveObject}
      />,
    );

    const canvas = screen.getByRole('img', { name: 'Canvas test drawing canvas' });
    const world = canvas?.querySelector('.drawing-canvas__world');

    expect(world).toHaveAttribute('transform', 'translate(36 36) scale(1)');

    fireEvent.pointerDown(canvas, { button: 0, pointerId: 11, clientX: 20, clientY: 30 });
    fireEvent.pointerMove(canvas, { pointerId: 11, clientX: 35, clientY: 18 });
    fireEvent.pointerUp(canvas, { pointerId: 11 });

    expect(world).toHaveAttribute('transform', 'translate(51 24) scale(1)');
    expect(onMoveObject).not.toHaveBeenCalled();
  });

  test('auto-fits large generated drawings on load', async () => {
    const { container } = render(
      <DrawingCanvas
        drawing={{ ...createDrawing(), width: 3456, height: 2592 }}
        selectedId={null}
        onSelectObject={vi.fn()}
        onMoveObject={vi.fn()}
      />,
    );

    const canvas = container.querySelector('.drawing-canvas__svg');
    expect(canvas).not.toBeNull();
    const world = canvas?.querySelector('.drawing-canvas__world');

    await waitFor(() => expect(world?.getAttribute('transform')).toContain('scale(0.'));
  });

  test('supports layer visibility, print boundary, and minimap overlays', () => {
    const hiddenSource: DrawingObject = {
      id: 'source-1',
      kind: 'source_fragment',
      label: 'Source evidence',
      points: [],
      bounds: { x: 5, y: 5, width: 50, height: 40 },
      style: baseStyle,
      sourceEvidenceIds: [],
    };
    const drawing = { ...createDrawing(), objects: [region, hiddenSource] };

    const { container } = render(
      <DrawingCanvas
        drawing={drawing}
        selectedId={null}
        hiddenLayerIds={['source']}
        showPrintBoundary
        showMinimap
        onSelectObject={vi.fn()}
        onMoveObject={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /Source evidence/ })).toBeNull();
    expect(container.querySelector('.drawing-canvas__print-boundary')).not.toBeNull();
    expect(container.querySelector('.drawing-minimap')).not.toBeNull();
    expect(screen.getByLabelText('Drawing minimap window')).toBeInTheDocument();
  });

  test('classifies semantic overlay separately from the source map layer', () => {
    const sourceMap: DrawingObject = {
      id: 'source-map-1',
      kind: 'source_fragment',
      label: 'Coordinate map',
      points: [],
      bounds: { x: 0, y: 0, width: 100, height: 60 },
      style: baseStyle,
      sourceEvidenceIds: [],
      metadata: { semanticSourceMap: true },
    };
    const semanticConnector: DrawingObject = {
      id: 'semantic-connector-1',
      kind: 'connector',
      label: '16"-CHWS-CS02',
      points: [
        { x: 10, y: 20 },
        { x: 90, y: 20 },
      ],
      bounds: { x: 10, y: 20, width: 80, height: 0 },
      style: baseStyle,
      sourceEvidenceIds: [],
      metadata: { semanticOverlay: true },
    };

    expect(objectLayerIds(sourceMap)).toContain('source');
    expect(objectLayerIds(sourceMap)).not.toContain('semantic');
    expect(objectLayerIds(semanticConnector)).toContain('semantic');
    expect(objectLayerIds(semanticConnector)).toContain('lines');
    expect(objectLayerIds(semanticConnector)).not.toContain('source');
  });

  test('keeps the minimap hidden until toggled on', () => {
    const { container } = render(
      <DrawingCanvas
        drawing={createDrawing()}
        selectedId={null}
        onSelectObject={vi.fn()}
        onMoveObject={vi.fn()}
      />,
    );

    expect(container.querySelector('.drawing-minimap')).toBeNull();
  });

  test('lets the floating minimap move and resize', async () => {
    const { container } = render(
      <DrawingCanvas
        drawing={createDrawing()}
        selectedId={null}
        showMinimap
        onSelectObject={vi.fn()}
        onMoveObject={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByLabelText('Drawing minimap window')).toBeInTheDocument());

    const window = container.querySelector('.drawing-minimap-window') as HTMLElement;
    const originalTransform = window.style.transform;
    const moveHandle = screen.getByLabelText('Move minimap');
    fireEvent.pointerDown(moveHandle, { button: 0, pointerId: 1, clientX: 20, clientY: 20 });
    fireEvent.pointerMove(moveHandle, { pointerId: 1, clientX: 90, clientY: 70 });
    fireEvent.pointerUp(moveHandle, { pointerId: 1 });
    expect(window.style.transform).not.toBe(originalTransform);

    const originalWidth = window.style.width;
    const resizeHandle = screen.getByLabelText('Resize minimap');
    fireEvent.pointerDown(resizeHandle, { button: 0, pointerId: 2, clientX: 220, clientY: 140 });
    fireEvent.pointerMove(resizeHandle, { pointerId: 2, clientX: 270, clientY: 180 });
    fireEvent.pointerUp(resizeHandle, { pointerId: 2 });
    expect(window.style.width).not.toBe(originalWidth);
  });
});
