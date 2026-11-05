import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import type { DrawingObject, DrawingStyle } from '../../types';
import { DrawingInspector } from './DrawingInspector';

const style: DrawingStyle = {
  stroke: '#334155',
  fill: '#ffffff',
  strokeWidth: 2,
  opacity: 1,
};

const selectedObject: DrawingObject = {
  id: 'region-1',
  kind: 'region',
  label: 'Area 1',
  points: [
    { x: 10, y: 10 },
    { x: 80, y: 50 },
  ],
  bounds: { x: 10, y: 10, width: 70, height: 40 },
  style,
  sourceEvidenceIds: [],
};

describe('DrawingInspector', () => {
  test('provides distinct accessible labels for color swatch and text inputs', () => {
    render(
      <DrawingInspector
        selectedObject={selectedObject}
        onUpdateLabel={vi.fn()}
        onUpdateStyle={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Stroke color swatch')).toHaveAttribute('type', 'color');
    expect(screen.getByLabelText('Stroke color value')).toHaveValue('#334155');
    expect(screen.getByLabelText('Fill color swatch')).toHaveAttribute('type', 'color');
    expect(screen.getByLabelText('Fill color value')).toHaveValue('#ffffff');
  });
});
