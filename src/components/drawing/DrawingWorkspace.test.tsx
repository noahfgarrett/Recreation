import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import type { DrawingDocument, DrawingStyle } from '../../types';
import { DrawingWorkspace } from './DrawingWorkspace';

const baseStyle: DrawingStyle = {
  stroke: '#dc2626',
  fill: 'transparent',
  strokeWidth: 2,
  opacity: 1,
};

afterEach(() => cleanup());

function createDrawing(): DrawingDocument {
  return {
    id: 'drawing-workspace-test',
    projectId: 'project-test',
    name: 'Workspace test drawing',
    width: 1200,
    height: 800,
    objects: [
      {
        id: 'pipe-1',
        kind: 'pipe',
        label: '12"-HHWS-CS02',
        points: [
          { x: 100, y: 100 },
          { x: 280, y: 100 },
        ],
        bounds: { x: 100, y: 100, width: 180, height: 0 },
        style: baseStyle,
        sourceEvidenceIds: ['src_hhw_02_p1'],
        metadata: {
          system: 'HHWS',
          sourceCandidateId: 'candidate-1',
          sheetRef: 'DEMO-ME-4HHW03',
          startConnectionType: 'pipe-junction',
          endConnectionType: 'dangling',
        },
      },
      {
        id: 'source-1',
        kind: 'source_fragment',
        label: 'Source hint',
        points: [],
        bounds: { x: 20, y: 20, width: 80, height: 60 },
        style: { ...baseStyle, stroke: '#94a3b8' },
        sourceEvidenceIds: [],
      },
    ],
    sourcePages: [
      {
        id: 'src_hhw_02_p1',
        sourceFileId: 'src_hhw_02',
        page: 1,
        width: 612,
        height: 792,
        rotation: 0,
        cropBounds: { x: 0, y: 0, width: 612, height: 792 },
        textSpans: [],
        vectorCount: 0,
        vectorSegments: [],
      },
    ],
    styles: { default: baseStyle },
    visualQa: {
      disconnectedContinuations: 1,
      lineTagRegister: [
        { tag: '12"-HHWS-CS02', system: 'HHWS', sourcePages: 2 },
        { tag: '10"-HHWR-CS02', system: 'HHWR', sourcePages: 1 },
      ],
      semanticRelationshipGraph: {
        metrics: { nodes: 5, edges: 4 },
        qa: {},
        nodes: [
          {
            id: 'line-hhws',
            kind: 'line_tag',
            tag: '12"-HHWS-CS02',
            system: 'HHWS',
            sourceFileId: 'src_hhw_02',
            page: 1,
            confidence: 0.92,
            bounds: { x: 140, y: 96, width: 84, height: 14 },
            metadata: { sourcePath: '/fixtures/DEMO-ME-4HHW02.pdf' },
          },
          {
            id: 'line-hhwr',
            kind: 'line_tag',
            tag: '10"-HHWR-CS02',
            system: 'HHWR',
            sourceFileId: 'src_hhw_02',
            page: 1,
            confidence: 0.9,
            bounds: { x: 140, y: 120, width: 86, height: 14 },
            metadata: { sourcePath: '/fixtures/DEMO-ME-4HHW02.pdf' },
          },
          {
            id: 'pump-1',
            kind: 'equipment',
            tag: 'R-DEMO-HHW-P-01',
            system: 'HHWS',
            sourceFileId: 'src_hhw_02',
            page: 1,
            confidence: 0.84,
            bounds: { x: 220, y: 168, width: 72, height: 20 },
            metadata: { sourcePath: '/fixtures/DEMO-ME-4HHW02.pdf' },
          },
          {
            id: 'pit-101',
            kind: 'instrument',
            tag: 'PIT-101',
            system: 'HHWS',
            sourceFileId: 'src_hhw_02',
            page: 1,
            confidence: 0.82,
            bounds: { x: 264, y: 88, width: 48, height: 18 },
            metadata: { sourcePath: '/fixtures/DEMO-ME-4HHW02.pdf' },
          },
          {
            id: 'cont-1',
            kind: 'continuation',
            tag: 'TO DEMO-ME-4HHW03',
            system: 'HHWS',
            sourceFileId: 'src_hhw_02',
            page: 1,
            confidence: 0.75,
            bounds: { x: 500, y: 94, width: 78, height: 20 },
            metadata: { sourcePath: '/fixtures/DEMO-ME-4HHW02.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-pump',
            kind: 'attached_to_line',
            sourceId: 'pump-1',
            targetId: 'line-hhws',
            lineTag: '12"-HHWS-CS02',
            system: 'HHWS',
            status: 'inferred',
            confidence: 0.84,
          },
          {
            id: 'edge-pit',
            kind: 'instrument_on_line',
            sourceId: 'pit-101',
            targetId: 'line-hhws',
            lineTag: '12"-HHWS-CS02',
            system: 'HHWS',
            status: 'inferred',
            confidence: 0.82,
          },
          {
            id: 'edge-cont',
            kind: 'continuation_on_line',
            sourceId: 'cont-1',
            targetId: 'line-hhws',
            lineTag: '12"-HHWS-CS02',
            system: 'HHWS',
            status: 'matched',
            confidence: 0.75,
          },
          {
            id: 'edge-continues',
            kind: 'continues_to',
            sourceId: 'line-hhws',
            targetId: 'line-hhwr',
            lineTag: '12"-HHWS-CS02',
            system: 'HHWS',
            status: 'matched',
            confidence: 0.7,
          },
        ],
      },
    },
  };
}

describe('DrawingWorkspace', () => {
  test('offers tabbed workstation layers, review queue, legend, minimap, and undo controls', () => {
    const onChange = vi.fn();
    const { container } = render(<DrawingWorkspace drawing={createDrawing()} selectedId="pipe-1" onChange={onChange} />);

    expect(screen.getByRole('tab', { name: /Layers/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /Reviews/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Legend/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Tree/ })).toBeInTheDocument();
    expect(container.querySelector('.drawing-minimap')).toBeNull();

    fireEvent.change(screen.getByLabelText('Text'), { target: { value: 'Renamed line' } });
    expect(screen.getByDisplayValue('Renamed line')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Undo'));
    expect(screen.getByDisplayValue('12"-HHWS-CS02')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Hide source map'));
    expect(screen.queryByRole('button', { name: 'source fragment Source hint' })).toBeNull();

    fireEvent.click(screen.getByTitle('Show minimap'));
    expect(container.querySelector('.drawing-minimap')).not.toBeNull();
    expect(screen.queryByRole('region', { name: 'Line tag register' })).toBeNull();

    fireEvent.click(screen.getByTitle('Show line tag register'));
    const lineTagDrawer = screen.getByRole('region', { name: 'Line tag register' });
    expect(lineTagDrawer).toBeInTheDocument();
    expect(within(lineTagDrawer).getByText('12"-HHWS-CS02')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Hide line tag register'));
    expect(screen.queryByRole('region', { name: 'Line tag register' })).toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: /Reviews/ }));
    expect(screen.getByRole('button', { name: /DEMO-ME-4HHW03/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dangling endpoint/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Legend/ }));
    expect(screen.getByText('HHWS')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Tree/ }));
    expect(screen.getByRole('tree', { name: 'P&ID relationship tree' })).toBeInTheDocument();
    expect(screen.getByText('HHWS System')).toBeInTheDocument();
    expect(screen.getByText('R-DEMO-HHW-P-01')).toBeInTheDocument();
    expect(screen.getByText('PIT-101')).toBeInTheDocument();
  });

  test('preserves undo history when used as a controlled drawing editor', () => {
    function ControlledWorkspace() {
      const [drawing, setDrawing] = useState(createDrawing());
      return <DrawingWorkspace drawing={drawing} selectedId="pipe-1" onChange={setDrawing} />;
    }

    render(<ControlledWorkspace />);

    fireEvent.change(screen.getByLabelText('Text'), { target: { value: 'Parent controlled rename' } });
    expect(screen.getByDisplayValue('Parent controlled rename')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Undo'));
    expect(screen.getByDisplayValue('12"-HHWS-CS02')).toBeInTheDocument();
  });

  test('opens the relationship tree as a central editable workbench separate from the canvas', () => {
    const { container } = render(<DrawingWorkspace drawing={createDrawing()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Tree workbench' }));

    expect(container.querySelector('.drawing-tree-workbench')).toBeInTheDocument();
    expect(screen.getByRole('tree', { name: 'P&ID relationship tree' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Indent' })).toBeInTheDocument();
    expect(container.querySelector('.drawing-canvas-shell')).toBeNull();
  });

  test('shows source evidence in the sidebar when a relationship tree tag is selected', () => {
    const { container } = render(<DrawingWorkspace drawing={createDrawing()} apiBaseUrl="http://127.0.0.1:8765" />);

    fireEvent.click(screen.getByRole('button', { name: 'Tree workbench' }));
    fireEvent.click(screen.getByRole('treeitem', { name: /R-DEMO-HHW-P-01/ }));

    const treeInspector = screen.getByLabelText('Tree source inspector');
    expect(screen.getByRole('heading', { name: 'Tree Source' })).toBeInTheDocument();
    expect(within(treeInspector).getByText('R-DEMO-HHW-P-01')).toBeInTheDocument();
    expect(within(treeInspector).getByText('DEMO-ME-4HHW02.pdf')).toBeInTheDocument();
    expect(within(treeInspector).getByText('Highlighted bounds available')).toBeInTheDocument();
    expect(container.querySelector('img[alt="src_hhw_02 page 1 source preview"]')).toHaveAttribute(
      'src',
      'http://127.0.0.1:8765/projects/project-test/sources/src_hhw_02/pages/1/image?dpi=96',
    );
    expect(container.querySelector('.tree-source-inspector__highlight')).toHaveStyle({
      left: '35.947712418300654%',
      top: '21.21212121212121%',
    });

    fireEvent.click(screen.getByRole('button', { name: 'View highlighted source' }));

    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(container.querySelector('img[alt="Page 1"]')).toHaveAttribute(
      'src',
      'http://127.0.0.1:8765/projects/project-test/sources/src_hhw_02/pages/1/image?dpi=150',
    );
  });

  test('surfaces the electrical legend sheet as source-trace context for tree rows', () => {
    const { container } = render(<DrawingWorkspace drawing={createElectricalGuideDrawing()} apiBaseUrl="http://127.0.0.1:8765" />);

    fireEvent.click(screen.getByRole('button', { name: 'Tree workbench' }));
    fireEvent.click(screen.getByRole('treeitem', { name: /GEN-15/ }));

    const treeInspector = screen.getByLabelText('Tree source inspector');
    expect(within(treeInspector).getByRole('heading', { name: 'Document guide' })).toBeInTheDocument();
    expect(within(treeInspector).getByText('Page 1')).toBeInTheDocument();
    expect(within(treeInspector).getByText('Building -> Power System -> Voltage -> Component -> Level -> Grid Location')).toBeInTheDocument();
    expect(within(treeInspector).getByText('MDP: Main Distribution Panel')).toBeInTheDocument();
    expect(within(treeInspector).getByText('SWG: Switchgear')).toBeInTheDocument();
    expect(container.querySelector('img[alt="src_elec page 1 document guide preview"]')).toHaveAttribute(
      'src',
      'http://127.0.0.1:8765/projects/project-test/sources/src_elec/pages/1/image?dpi=96',
    );
  });

  test('opens the source document page for the selected drawing object', () => {
    const { container } = render(<DrawingWorkspace drawing={createDrawing()} selectedId="pipe-1" apiBaseUrl="http://127.0.0.1:8765" />);

    expect(screen.getByRole('heading', { name: 'Source Document' })).toBeInTheDocument();
    expect(screen.getByText('src_hhw_02')).toBeInTheDocument();
    expect(screen.getByText('Page 1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /View source page/ }));

    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(container.querySelector('img[alt="Page 1"]')).toHaveAttribute(
      'src',
      'http://127.0.0.1:8765/projects/project-test/sources/src_hhw_02/pages/1/image?dpi=150',
    );
  });

  test('lets users place, recolor, and resize symbols from the symbol library', () => {
    const onChange = vi.fn();
    const { container } = render(<DrawingWorkspace drawing={createDrawing()} onChange={onChange} />);

    fireEvent.click(screen.getByRole('tab', { name: /Symbols/ }));
    expect(screen.getByText('Recreation vector pack')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Master sheet' })).toHaveAttribute('href', '/pid-symbols/symbol-master.svg');

    fireEvent.click(screen.getByTitle('Place Pump'));

    expect(screen.getByDisplayValue('Pump')).toBeInTheDocument();
    const placed = onChange.mock.calls.at(-1)?.[0] as DrawingDocument;
    const pump = placed.objects.find((object) => object.metadata?.symbolType === 'pump');
    expect(pump).toMatchObject({
      kind: 'symbol',
      metadata: expect.objectContaining({
        symbolRegistry: 'recreation-vector-pack',
        userPlacedSymbol: true,
      }),
    });
    expect(container.querySelector('[data-testid="pid-symbol-pump"]')).toBeInTheDocument();

    // Query inside the inspector: with the symbol palette open, a page-wide getByLabelText
    // walks hundreds of symbol nodes and took ~10 s in jsdom.
    const inspector = within(container.querySelector('aside[aria-label="Drawing inspector"]') as HTMLElement);
    fireEvent.change(inspector.getByLabelText('Stroke color value'), { target: { value: '#2563eb' } });
    fireEvent.change(inspector.getByLabelText('W'), { target: { value: '88' } });

    const resized = onChange.mock.calls.at(-1)?.[0] as DrawingDocument;
    const resizedPump = resized.objects.find((object) => object.metadata?.symbolType === 'pump');
    expect(resizedPump?.style.stroke).toBe('#2563eb');
    expect(resizedPump?.bounds.width).toBe(88);
  });
});

function createElectricalGuideDrawing(): DrawingDocument {
  return {
    id: 'electrical-guide-workspace-test',
    projectId: 'project-test',
    name: 'Electrical guide workspace test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [
      {
        id: 'src_elec_p1',
        sourceFileId: 'src_elec',
        page: 1,
        width: 3024,
        height: 2160,
        rotation: 0,
        cropBounds: { x: 0, y: 0, width: 3024, height: 2160 },
        textSpans: [],
        vectorCount: 0,
        vectorSegments: [],
      },
      {
        id: 'src_elec_p180',
        sourceFileId: 'src_elec',
        page: 180,
        width: 3024,
        height: 2160,
        rotation: 0,
        cropBounds: { x: 0, y: 0, width: 3024, height: 2160 },
        textSpans: [],
        vectorCount: 0,
        vectorSegments: [],
      },
    ],
    styles: {},
    visualQa: {
      electricalRelationshipGraph: {
        metrics: {
          nodes: 2,
          edges: 1,
          documentGuide: {
            sourcePages: [{ sourceFileId: 'src_elec', page: 1, pageId: 'src_elec_p1' }],
            abbreviations: {
              MDP: 'MAIN DISTRIBUTION PANEL',
              SWG: 'SWITCHGEAR',
            },
            equipmentTagSchema: ['BUILDING', 'POWER SYSTEM', 'VOLTAGE', 'COMPONENT', 'LEVEL', 'GRID LOCATION'],
          },
        },
        qa: {},
        nodes: [
          {
            id: 'mdp',
            kind: 'line_tag',
            tag: 'RW4MDP4C6',
            system: 'ELEC',
            sourceFileId: 'src_elec',
            page: 180,
            confidence: 0.94,
            bounds: { x: 884, y: 620, width: 92, height: 14 },
            metadata: { sourcePath: '/fixtures/Electrical Package.pdf' },
          },
          {
            id: 'generator',
            kind: 'equipment',
            tag: 'GEN-15',
            system: 'ELEC',
            sourceFileId: 'src_elec',
            page: 180,
            confidence: 0.94,
            bounds: { x: 1140, y: 430, width: 68, height: 18 },
            metadata: { sourcePath: '/fixtures/Electrical Package.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-generator',
            kind: 'attached_to_line',
            sourceId: 'generator',
            targetId: 'mdp',
            lineTag: 'RW4MDP4C6',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.94,
          },
        ],
      },
    },
  };
}
