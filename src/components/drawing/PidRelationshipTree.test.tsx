import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import type { DrawingDocument } from '../../types';
import { buildRelationshipTreeRows, PidRelationshipTree, relationshipTreeRowsToCsv, relationshipTreeRowsToXlsxBlob } from './PidRelationshipTree';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('PidRelationshipTree', () => {
  test('builds a system hierarchy from extracted line, equipment, instrument, and continuation relationships', () => {
    const rows = buildRelationshipTreeRows(createTreeDrawing());

    expect(rows.map((row) => row.tag)).toEqual(expect.arrayContaining(['CDA System', '6"-CDA-CS01', 'R-CDA-C-04', 'PIT-420', 'XV-420', 'TO DEMO-ME-4CDA02', '3"-IA-CT01', 'Unresolved / needs review', 'Loose note tag']));
    expect(rows.find((row) => row.tag === 'R-CDA-C-04')).toMatchObject({
      depth: 2,
      relationship: 'attached_to_line',
      parentTag: '6"-CDA-CS01',
      status: 'inferred',
    });
    expect(rows.find((row) => row.tag === 'Loose note tag')).toMatchObject({
      depth: 1,
      relationship: 'unresolved',
      parentTag: 'Unresolved / needs review',
    });
    expect(rows.find((row) => row.tag === '3"-IA-CT01')).toMatchObject({
      depth: 2,
      relationship: 'continues to',
      parentTag: '6"-CDA-CS01',
    });
    expect(rows.find((row) => row.tag === 'XV-420')).toMatchObject({
      depth: 3,
      relationship: 'device_on_equipment',
      parentTag: 'R-CDA-C-04',
    });
  });

  test('renders electrical switchgear sections as tree roots with nested equipment and panels', () => {
    const rows = buildRelationshipTreeRows(createElectricalSectionDrawing());

    expect(rows.map((row) => row.tag)).toEqual(expect.arrayContaining(['ELEC System', 'SW A (SECTION 1)', 'SW A TRANSFORMER', 'MAIN BREAKER (SECTION 2)', 'RW4MDP4F21']));
    expect(rows.find((row) => row.tag === 'SW A (SECTION 1)')).toMatchObject({
      depth: 1,
      kind: 'section',
      relationship: 'section',
    });
    expect(rows.find((row) => row.tag === 'SW A TRANSFORMER')).toMatchObject({
      depth: 2,
      relationship: 'equipment_on_section',
      parentTag: 'SW A (SECTION 1)',
    });
    expect(rows.find((row) => row.tag === 'MAIN BREAKER (SECTION 2)')).toMatchObject({
      depth: 3,
      relationship: 'device_on_equipment',
      parentTag: 'SW A TRANSFORMER',
    });
    expect(rows.find((row) => row.tag === 'RW4MDP4F21')).toMatchObject({
      depth: 4,
      relationship: 'feeds_panel',
      parentTag: 'MAIN BREAKER (SECTION 2)',
    });
  });

  test('merges electrical and semantic relationship graphs for mixed discipline uploads', () => {
    const rows = buildRelationshipTreeRows(createMixedDisciplineDrawing());

    expect(rows.map((row) => row.tag)).toEqual(expect.arrayContaining(['Electrical', 'Mechanical', 'ELEC System', 'CDA System', 'SW A (SECTION 1)', 'R-CDA-C-04']));
    expect(rows.find((row) => row.tag === 'Electrical')).toMatchObject({
      depth: 0,
      kind: 'discipline',
      relationship: 'discipline',
    });
    expect(rows.find((row) => row.tag === 'ELEC System')).toMatchObject({
      depth: 1,
      relationship: 'system',
      parentTag: 'Electrical',
    });
    expect(rows.find((row) => row.tag === 'SW A (SECTION 1)')).toMatchObject({
      depth: 2,
      relationship: 'section',
      parentTag: 'ELEC System',
    });
    expect(rows.find((row) => row.tag === 'Mechanical')).toMatchObject({
      depth: 0,
      kind: 'discipline',
    });
    expect(rows.find((row) => row.tag === 'R-CDA-C-04')).toMatchObject({
      depth: 3,
      relationship: 'attached_to_line',
      parentTag: '6"-CDA-CS01',
    });
  });

  test('preserves semantic rows when a mixed discipline upload has a shared electrical hierarchy view', () => {
    const drawing = createMixedDisciplineDrawing();
    const electricalGraph = drawing.visualQa.electricalRelationshipGraph as { nodes: unknown[]; edges: unknown[] };
    drawing.visualQa.hierarchyViews = [
      {
        id: 'electrical_power',
        label: 'Electrical Power Tree',
        discipline: 'Electrical',
        nodes: electricalGraph.nodes,
        edges: electricalGraph.edges,
      },
    ];

    const rows = buildRelationshipTreeRows(drawing);

    expect(rows.map((row) => row.tag)).toEqual(expect.arrayContaining(['Electrical', 'Mechanical', 'ELEC System', 'CDA System', 'SW A (SECTION 1)', 'R-CDA-C-04']));
    expect(rows.find((row) => row.tag === 'R-CDA-C-04')).toMatchObject({
      depth: 3,
      relationship: 'attached_to_line',
      parentTag: '6"-CDA-CS01',
    });
  });

  test('exports relationship rows as CSV and XLSX from the workbench tab', () => {
    const rows = buildRelationshipTreeRows(createTreeDrawing());
    const csv = relationshipTreeRowsToCsv(rows);
    const xlsx = relationshipTreeRowsToXlsxBlob(rows);

    expect(csv).toContain('6""-CDA-CS01');
    expect(csv).toContain('R-CDA-C-04');
    expect(xlsx.type).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    expect(xlsx.size).toBeGreaterThan(1000);

    const createObjectUrl = vi.fn(() => 'blob:relationship-tree');
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    render(<PidRelationshipTree drawing={createTreeDrawing()} />);

    fireEvent.click(screen.getByRole('button', { name: 'CSV' }));
    fireEvent.click(screen.getByRole('button', { name: 'XLSX' }));

    expect(createObjectUrl).toHaveBeenCalledTimes(2);
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:relationship-tree');
    expect(click).toHaveBeenCalledTimes(2);
  });

  test('allows the workbench tree to reorder and indent rows for user-polished hierarchies', () => {
    render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" />);

    const pitRow = screen.getByRole('treeitem', { name: /PIT-420/ });
    fireEvent.click(pitRow);
    fireEvent.click(screen.getByRole('button', { name: 'Move up' }));
    fireEvent.click(screen.getByRole('button', { name: 'Indent' }));

    const rows = screen.getAllByRole('treeitem').map((row) => row.textContent || '');
    const pitIndex = rows.findIndex((row) => row.includes('PIT-420'));
    const compressorIndex = rows.findIndex((row) => row.includes('R-CDA-C-04'));

    expect(pitIndex).toBeGreaterThanOrEqual(0);
    expect(compressorIndex).toBeGreaterThanOrEqual(0);
    expect(pitIndex).toBeLessThan(compressorIndex);
    expect(screen.getByRole('treeitem', { name: /PIT-420/ })).toHaveAttribute('aria-level', '4');
  });

  test('supports ctrl or command click to add and subtract selected hierarchy rows', () => {
    render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" />);

    const compressorRow = screen.getByRole('treeitem', { name: /R-CDA-C-04/ });
    const pitRow = screen.getByRole('treeitem', { name: /PIT-420/ });

    fireEvent.click(compressorRow);
    fireEvent.click(pitRow, { ctrlKey: true });

    expect(compressorRow).toHaveAttribute('aria-selected', 'true');
    expect(pitRow).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(compressorRow, { metaKey: true });

    expect(compressorRow).toHaveAttribute('aria-selected', 'false');
    expect(pitRow).toHaveAttribute('aria-selected', 'true');
  });

  test('supports shift click range selection and applies indent to all selected rows', () => {
    render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" />);

    const compressorRow = screen.getByRole('treeitem', { name: /R-CDA-C-04/ });
    const pitRow = screen.getByRole('treeitem', { name: /PIT-420/ });

    fireEvent.click(compressorRow);
    fireEvent.click(pitRow, { shiftKey: true });
    fireEvent.click(screen.getByRole('button', { name: 'Indent' }));

    expect(compressorRow).toHaveAttribute('aria-selected', 'true');
    expect(pitRow).toHaveAttribute('aria-selected', 'true');
    expect(compressorRow).toHaveAttribute('aria-level', '4');
    expect(pitRow).toHaveAttribute('aria-level', '4');
  });

  test('drags selected hierarchy rows as a group while preserving their order', () => {
    render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" />);

    const compressorRow = screen.getByRole('treeitem', { name: /R-CDA-C-04/ });
    const unresolvedRow = screen.getByRole('treeitem', { name: /Unresolved \/ needs review/ });

    fireEvent.click(compressorRow);
    fireEvent.click(screen.getByRole('treeitem', { name: /XV-420/ }), { ctrlKey: true });
    fireEvent.dragStart(compressorRow);
    fireEvent.drop(unresolvedRow);

    const rowTexts = screen.getAllByRole('treeitem').map((row) => row.textContent || '');
    const groupStart = rowTexts.findIndex((row) => row.includes('R-CDA-C-04'));
    const unresolvedIndex = rowTexts.findIndex((row) => row.includes('Unresolved / needs review'));

    expect(groupStart).toBeGreaterThanOrEqual(0);
    expect(unresolvedIndex).toBeGreaterThan(groupStart);
    expect(rowTexts.slice(groupStart, groupStart + 2).join('|')).toContain('R-CDA-C-04');
    expect(rowTexts.slice(groupStart, groupStart + 2).join('|')).toContain('XV-420');
  });

  test('supports marquee selection across visible hierarchy rows', () => {
    const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;
    HTMLElement.prototype.getBoundingClientRect = function getTreeTestRect() {
      const text = this.textContent || '';
      const rows = ['6"-CDA-CS01', 'R-CDA-C-04', 'PIT-420', 'XV-420'];
      const index = rows.findIndex((tag) => text.includes(tag));
      if (this.classList.contains('pid-relationship-tree__rows')) {
        return { x: 0, y: 0, left: 0, top: 0, right: 900, bottom: 240, width: 900, height: 240, toJSON: () => ({}) };
      }
      if (index >= 0) {
        const top = 20 + index * 34;
        return { x: 0, y: top, left: 0, top, right: 900, bottom: top + 30, width: 900, height: 30, toJSON: () => ({}) };
      }
      return originalGetBoundingClientRect.call(this);
    };

    try {
      render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" />);

      const rowContainer = screen.getByRole('tree', { name: 'P&ID relationship tree' });
      fireEvent.mouseDown(rowContainer, { clientX: 4, clientY: 50 });
      fireEvent.mouseMove(rowContainer, { clientX: 880, clientY: 118 });
      fireEvent.mouseUp(rowContainer, { clientX: 880, clientY: 118 });

      expect(screen.getByRole('treeitem', { name: /R-CDA-C-04/ })).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByRole('treeitem', { name: /PIT-420/ })).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByRole('treeitem', { name: /XV-420/ })).toHaveAttribute('aria-selected', 'false');
    } finally {
      HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
    }
  });

  test('zooms the workbench tree rows for easier hierarchy review', () => {
    render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" />);

    const rowContainer = screen.getByRole('tree', { name: 'P&ID relationship tree' });
    expect(rowContainer).toHaveStyle({ '--tree-zoom': '1' });

    fireEvent.click(screen.getByRole('button', { name: 'Zoom tree in' }));

    expect(rowContainer).toHaveStyle({ '--tree-zoom': '1.1' });
    expect(screen.getByText('110%')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Zoom tree out' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset tree zoom' }));

    expect(rowContainer).toHaveStyle({ '--tree-zoom': '1' });
  });

  test('passes source bounds through when a workbench row is selected', () => {
    const onSelectRow = vi.fn();
    render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" onSelectRow={onSelectRow} />);

    fireEvent.click(screen.getByRole('treeitem', { name: /R-CDA-C-04/ }));

    expect(onSelectRow).toHaveBeenCalledWith(
      expect.objectContaining({
        tag: 'R-CDA-C-04',
        sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf',
        sourceBounds: { page: 1, x: 220, y: 360, width: 64, height: 32 },
      }),
    );
  });

  test('renders confidence as a quiet engineering marker instead of a pill badge', () => {
    const { container } = render(<PidRelationshipTree drawing={createTreeDrawing()} mode="workbench" />);

    expect(screen.getByLabelText('Confidence 90%')).toBeInTheDocument();
    const confidenceMarker = container.querySelector('.pid-relationship-tree__confidence--high');
    expect(confidenceMarker).not.toBeNull();
    expect(confidenceMarker?.querySelector('b')?.textContent).toBe('94%');
  });

  test('exports smartsheet-ready hierarchy values with visible indentation', () => {
    const rows = buildRelationshipTreeRows(createTreeDrawing());
    const csv = relationshipTreeRowsToCsv(rows);

    expect(csv).toContain('Smartsheet Primary');
    expect(csv).toContain('Equipment Description');
    expect(csv).toContain('Source Path');
    expect(csv).toContain('Source Bounds');
    expect(csv).toContain('"    R-CDA-C-04"');
    expect(csv).toContain('"      XV-420"');
    expect(csv).toContain('/packages/reviewed/DEMO-ME-4CDA01.pdf');
    expect(csv).toContain('p1 x220 y360 w64 h32');
  });

  test('renders equipment component hierarchies even when no line tags are available', () => {
    const rows = buildRelationshipTreeRows(createComponentOnlyDrawing());

    expect(rows.map((row) => row.tag)).toEqual(expect.arrayContaining(['Mechanical', 'SA System', 'R-SA-FCU-102', 'FCU-102-TCV-01']));
    expect(rows.find((row) => row.tag === 'R-SA-FCU-102')).toMatchObject({
      relationship: 'equipment',
      parentTag: 'SA System',
    });
    expect(rows.find((row) => row.tag === 'FCU-102-TCV-01')).toMatchObject({
      relationship: 'equipment_component',
      parentTag: 'R-SA-FCU-102',
    });
  });

  test('deduplicates repeated physical tags while preserving child branches from each sighting', () => {
    const rows = buildRelationshipTreeRows(createDuplicateTagDrawing());
    const cdaLineRows = rows.filter((row) => row.tag === '6"-CDA-CS01');
    const compressorRows = rows.filter((row) => row.tag === 'R-CDA-C-04');

    expect(cdaLineRows).toHaveLength(1);
    expect(compressorRows).toHaveLength(1);
    expect(rows.find((row) => row.tag === 'PIT-421')).toMatchObject({
      parentTag: '6"-CDA-CS01',
      relationship: 'instrument_on_line',
    });
    expect(rows.find((row) => row.tag === 'XV-421')).toMatchObject({
      parentTag: 'R-CDA-C-04',
      relationship: 'device_on_equipment',
    });
  });

  test('nests systems under inferred building roots before equipment and children', () => {
    const rows = buildRelationshipTreeRows(createBuildingHierarchyDrawing());

    expect(rows.find((row) => row.tag === 'DEMO Building')).toMatchObject({
      depth: 0,
      kind: 'building',
      relationship: 'building',
    });
    expect(rows.find((row) => row.tag === 'CDA System')).toMatchObject({
      depth: 1,
      parentTag: 'DEMO Building',
      relationship: 'system',
    });
    expect(rows.find((row) => row.tag === '6"-CDA-CS01')).toMatchObject({
      depth: 2,
      parentTag: 'CDA System',
    });
    expect(rows.find((row) => row.tag === 'R-CDA-C-04')).toMatchObject({
      depth: 3,
      parentTag: '6"-CDA-CS01',
    });
  });

  test('keeps matching tags separate when they belong to different buildings', () => {
    const rows = buildRelationshipTreeRows(createDuplicateTagsAcrossBuildingsDrawing());

    expect(rows.find((row) => row.tag === 'DEMO Building')).toMatchObject({
      relationship: 'building',
    });
    expect(rows.find((row) => row.tag === 'DEMX Building')).toMatchObject({
      relationship: 'building',
    });
    expect(rows.filter((row) => row.tag === 'CDA System')).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ parentTag: 'DEMO Building' }),
        expect.objectContaining({ parentTag: 'DEMX Building' }),
      ]),
    );
    expect(rows.filter((row) => row.tag === '6"-CDA-CS01')).toHaveLength(2);
    expect(rows.filter((row) => row.tag === 'R-CDA-C-04')).toHaveLength(2);
  });

  test('uses building as the top hierarchy parent across mixed disciplines', () => {
    const rows = buildRelationshipTreeRows(createMixedDisciplinesSameBuildingDrawing());

    expect(rows.filter((row) => row.tag === 'DEMO Building')).toHaveLength(1);
    expect(rows.find((row) => row.tag === 'DEMO Building')).toMatchObject({
      depth: 0,
      relationship: 'building',
      parentTag: '',
    });
    expect(rows.find((row) => row.tag === 'CDA System')).toMatchObject({
      depth: 1,
      parentTag: 'DEMO Building',
    });
    expect(rows.find((row) => row.tag === 'ELEC System')).toMatchObject({
      depth: 1,
      parentTag: 'DEMO Building',
    });
    expect(rows.map((row) => row.tag)).not.toEqual(expect.arrayContaining(['Mechanical', 'Electrical']));
  });

  test('builds electrical equipment-only flow rows without ratings, devices, buses, or resolved compound targets', () => {
    const rows = buildRelationshipTreeRows(createElectricalEquipmentFlowDrawing(), { viewMode: 'equipment' });
    const tags = rows.map((row) => row.tag);

    expect(tags).toEqual(expect.arrayContaining(['ELEC System', 'RW4MDP4C6', 'GEN-15', 'RW4SWG2F6', 'RW4SS3D26', 'RW4SS3F26', 'RS2PP1B4', 'RS2PP1B4 CKT 1']));
    expect(tags).not.toEqual(expect.arrayContaining(['52', "5000A 'SWING' BUS", 'RW4SS3D26 & F26']));
    expect(rows.find((row) => row.tag === 'GEN-15')).toMatchObject({
      depth: 1,
      parentTag: 'ELEC System',
    });
    expect(rows.find((row) => row.tag === 'RW4SWG2F6')).toMatchObject({
      depth: 2,
      parentTag: 'GEN-15',
      equipmentDescription: 'Switchgear',
    });
    expect(rows.find((row) => row.tag === 'RS2PP1B4')).toMatchObject({
      relationship: 'panel_schedule_feeds',
      parentTag: 'RW4MDP4C6',
      equipmentDescription: 'Power Panel',
    });
    expect(rows.find((row) => row.tag === 'RS2PP1B4 CKT 1')).toMatchObject({
      relationship: 'panel_circuit',
      parentTag: 'RS2PP1B4',
      equipmentDescription: 'Recp Subfab 204 Col B3',
    });
    expect(rows.find((row) => row.tag === 'RW4MDP4C6')).toMatchObject({
      equipmentDescription: 'Main Distribution Panel',
    });
    expect(rows.find((row) => row.tag === 'GEN-15')).toMatchObject({
      equipmentDescription: 'Generator',
    });
    expect(relationshipTreeRowsToCsv(rows)).toContain('Equipment Description');
    expect(relationshipTreeRowsToCsv(rows)).toContain('Main Distribution Panel');
  });

  test('prefers shared hierarchy views over legacy electrical relationship graphs', () => {
    const drawing = createElectricalEquipmentFlowDrawing();
    drawing.visualQa.hierarchyViews = [
      {
        id: 'process_flow',
        label: 'Process Flow Tree',
        discipline: 'Process / P&ID',
        nodes: [
          {
            id: 'p1',
            kind: 'equipment',
            tag: 'P-101',
            system: 'CHW',
            sourceFileId: 'pid-source',
            page: 1,
            confidence: 0.94,
            metadata: { equipmentDescription: 'Pump', sourcePath: '/packages/PID.pdf' },
          },
          {
            id: 'l1',
            kind: 'line_tag',
            tag: '6"-CHW-001',
            system: 'CHW',
            sourceFileId: 'pid-source',
            page: 1,
            confidence: 0.91,
          },
          {
            id: 'ft1',
            kind: 'instrument',
            tag: 'FT-101',
            system: 'CHW',
            sourceFileId: 'pid-source',
            page: 1,
            confidence: 0.88,
          },
        ],
        edges: [
          {
            id: 'edge-pump-line',
            kind: 'process_flow',
            source: 'p1',
            target: 'l1',
            status: 'confirmed',
            confidence: 0.9,
          },
          {
            id: 'edge-line-ft',
            kind: 'line_mounted_item',
            source: 'l1',
            target: 'ft1',
            status: 'inferred',
            confidence: 0.87,
          },
        ],
      },
    ];

    const rows = buildRelationshipTreeRows(drawing);

    expect(rows.map((row) => row.tag)).toEqual(expect.arrayContaining(['P-101', 'FT-101']));
    expect(rows.map((row) => row.tag)).not.toContain('GEN-15');
    expect(rows.find((row) => row.tag === 'FT-101')).toMatchObject({
      relationship: 'line_mounted_item',
      parentTag: '6"-CHW-001',
    });
  });

  test('defaults electrical workbench to equipment flow and can switch back to the full source graph', () => {
    render(<PidRelationshipTree drawing={createElectricalEquipmentFlowDrawing()} mode="workbench" />);

    expect(screen.getByRole('button', { name: 'Equipment Flow' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('treeitem', { name: /52/ })).toBeNull();
    expect(screen.queryByRole('treeitem', { name: /RW4SS3D26 & F26/ })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Full Graph' }));

    expect(screen.getByRole('button', { name: 'Full Graph' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('treeitem', { name: /52/ })).toBeInTheDocument();
    expect(screen.getByRole('treeitem', { name: /RW4SS3D26 & F26/ })).toBeInTheDocument();
  });

  test('collapses and expands hierarchy branches in equipment and full graph views', () => {
    render(<PidRelationshipTree drawing={createElectricalEquipmentFlowDrawing()} mode="workbench" />);

    expect(screen.getByRole('treeitem', { name: /RW4SS3D26/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse RW4SWG2F6 branch' }));

    expect(screen.getByRole('button', { name: 'Expand RW4SWG2F6 branch' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('treeitem', { name: /RW4SS3D26/ })).toBeNull();
    expect(screen.queryByRole('treeitem', { name: /RW4SS3F26/ })).toBeNull();
    expect(screen.getByText(/visible/)).toHaveTextContent('6 / 8 visible');

    fireEvent.click(screen.getByRole('button', { name: 'Expand all branches' }));

    expect(screen.getByRole('treeitem', { name: /RW4SS3D26/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Collapse all branches' }));

    expect(screen.queryByRole('treeitem', { name: /GEN-15/ })).toBeNull();
    expect(screen.queryByRole('treeitem', { name: /RS2PP1B4/ })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Full Graph' }));

    expect(screen.queryByRole('treeitem', { name: /52/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Expand all branches' }));
    expect(screen.getByRole('treeitem', { name: /52/ })).toBeInTheDocument();
  });

  test('builds dependency view rows from real equipment dependency edges', () => {
    const rows = buildRelationshipTreeRows(createDependencyDrawing(), { viewMode: 'dependency' });

    expect(rows.map((row) => row.tag)).toEqual([
      'R-CW-P-03',
      'VFD-R-CW-P-03',
      'RW4PP1E4',
      'RW4MDP4C6',
      'R-CW-P-03-MTR',
      'BAS-CP-01',
      'PIT-R-CW-P-03',
    ]);
    expect(rows.find((row) => row.tag === 'R-CW-P-03')).toMatchObject({
      depth: 0,
      relationship: 'target_equipment',
      status: 'registered',
    });
    expect(rows.find((row) => row.tag === 'VFD-R-CW-P-03')).toMatchObject({
      depth: 1,
      relationship: 'requires_drive',
      parentTag: 'R-CW-P-03',
      status: 'inferred',
    });
    expect(rows.find((row) => row.tag === 'RW4PP1E4')).toMatchObject({
      depth: 1,
      relationship: 'requires_power',
      parentTag: 'R-CW-P-03',
      status: 'confirmed',
    });
    expect(rows.find((row) => row.tag === 'PIT-R-CW-P-03')).toMatchObject({
      depth: 1,
      relationship: 'requires_instrument',
      parentTag: 'R-CW-P-03',
      status: 'needs_review',
      sourceDiscipline: 'Instrumentation & Control',
    });
  });

  test('renders dependency view toggle with status badges and filters', () => {
    render(<PidRelationshipTree drawing={createDependencyDrawing()} mode="workbench" />);

    expect(screen.getByRole('button', { name: 'Equipment Flow' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Full Graph' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Dependency View' }));

    expect(screen.getByRole('button', { name: 'Dependency View' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByRole('treeitem', { name: /R-CW-P-03/ })[0]).toHaveTextContent('Target Equipment');
    expect(screen.getByRole('treeitem', { name: /RW4PP1E4/ })).toHaveTextContent('Confirmed');
    expect(screen.getByRole('treeitem', { name: /R-CW-P-03-MTR/ })).toHaveTextContent('Inferred');

    fireEvent.click(screen.getByRole('checkbox', { name: 'Inferred' }));

    expect(screen.getByRole('treeitem', { name: /RW4PP1E4/ })).toBeInTheDocument();
    expect(screen.queryByRole('treeitem', { name: /R-CW-P-03-MTR/ })).toBeNull();
  });

  test('collapses and expands dependency target branches', () => {
    render(<PidRelationshipTree drawing={createDependencyDrawing()} mode="workbench" />);

    fireEvent.click(screen.getByRole('button', { name: 'Dependency View' }));
    expect(screen.getByRole('treeitem', { name: /RW4PP1E4/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Collapse R-CW-P-03 branch' }));

    expect(screen.getByRole('button', { name: 'Expand R-CW-P-03 branch' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('treeitem', { name: /RW4PP1E4/ })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Expand all branches' }));

    expect(screen.getByRole('treeitem', { name: /RW4PP1E4/ })).toBeInTheDocument();
  });

  test('exports dependency view rows as JSON, CSV, and XLSX matrix data', async () => {
    const rows = buildRelationshipTreeRows(createDependencyDrawing(), { viewMode: 'dependency' });
    const csv = relationshipTreeRowsToCsv(rows);
    const xlsx = relationshipTreeRowsToXlsxBlob(rows);

    expect(csv).toContain('Target Equipment Tag');
    expect(csv).toContain('Target Discipline');
    expect(csv).toContain('Depends On Equipment Tag');
    expect(csv).toContain('Dependency Discipline');
    expect(csv).toContain('Dependency Path');
    expect(csv).toContain('Commissioning Use');
    expect(csv).toContain('R-CW-P-03,Condenser water pump,Mechanical,VFD-R-CW-P-03');
    expect(csv).toContain('VFD-R-CW-P-03');
    expect(csv).toContain('RW4PP1E4');
    expect(csv).not.toContain('Smartsheet Primary');
    expect(xlsx.type).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    expect(xlsx.size).toBeGreaterThan(1000);

    const blobs: Blob[] = [];
    const createObjectUrl = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return `blob:dependency-${blobs.length}`;
    });
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    render(<PidRelationshipTree drawing={createDependencyDrawing()} mode="workbench" />);
    fireEvent.click(screen.getByRole('button', { name: 'Dependency View' }));
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    fireEvent.click(screen.getByRole('button', { name: 'CSV' }));
    fireEvent.click(screen.getByRole('button', { name: 'XLSX' }));

    expect(createObjectUrl).toHaveBeenCalledTimes(3);
    expect(click).toHaveBeenCalledTimes(3);
    expect(blobs[0].type).toBe('application/json;charset=utf-8');
  });
});

function createTreeDrawing(): DrawingDocument {
  return {
    id: 'tree-test',
    projectId: 'project-test',
    name: 'Single P&ID tree test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      semanticRelationshipGraph: {
        metrics: { nodes: 7, edges: 5 },
        qa: {},
        nodes: [
          {
            id: 'line-cda',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'reviewed-cda-01',
            page: 1,
            confidence: 0.94,
          },
          {
            id: 'line-ia',
            kind: 'line_tag',
            tag: '3"-IA-CT01',
            system: 'CDA',
            sourceFileId: 'reviewed-cda-01',
            page: 1,
            confidence: 0.88,
          },
          {
            id: 'compressor',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'reviewed-cda-01',
            page: 1,
            confidence: 0.9,
            bounds: { x: 220, y: 360, width: 64, height: 32 },
            metadata: { sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf' },
          },
          {
            id: 'pit-420',
            kind: 'instrument',
            tag: 'PIT-420',
            system: 'CDA',
            sourceFileId: 'reviewed-cda-01',
            page: 1,
            confidence: 0.86,
          },
          {
            id: 'xv-420',
            kind: 'device',
            tag: 'XV-420',
            system: 'CDA',
            sourceFileId: 'reviewed-cda-01',
            page: 1,
            confidence: 0.82,
          },
          {
            id: 'continuation-1',
            kind: 'continuation',
            tag: 'TO DEMO-ME-4CDA02',
            system: 'CDA',
            sourceFileId: 'reviewed-cda-01',
            page: 1,
            confidence: 0.8,
          },
          {
            id: 'loose-note',
            kind: 'label',
            tag: 'Loose note tag',
            system: 'CDA',
            sourceFileId: 'reviewed-cda-01',
            page: 1,
            confidence: 0.5,
          },
        ],
        edges: [
          {
            id: 'edge-compressor',
            kind: 'attached_to_line',
            sourceId: 'compressor',
            targetId: 'line-cda',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.9,
          },
          {
            id: 'edge-pit',
            kind: 'instrument_on_line',
            sourceId: 'pit-420',
            targetId: 'line-cda',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.86,
          },
          {
            id: 'edge-xv',
            kind: 'device_on_equipment',
            sourceId: 'xv-420',
            targetId: 'compressor',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.82,
          },
          {
            id: 'edge-continuation',
            kind: 'continuation_on_line',
            sourceId: 'continuation-1',
            targetId: 'line-cda',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'unmatched',
            confidence: 0.8,
          },
          {
            id: 'edge-continues',
            kind: 'continues_to',
            sourceId: 'line-cda',
            targetId: 'line-ia',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'matched',
            confidence: 0.78,
          },
        ],
      },
    },
  };
}

function createElectricalSectionDrawing(): DrawingDocument {
  return {
    id: 'elec-section-test',
    projectId: 'project-test',
    name: 'Electrical section tree test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      electricalRelationshipGraph: {
        metrics: { nodes: 4, edges: 3 },
        qa: {},
        nodes: [
          {
            id: 'section-a',
            kind: 'section',
            tag: 'SW A (SECTION 1)',
            system: 'ELEC',
            sourceFileId: 'elec-01',
            page: 1,
            confidence: 0.88,
          },
          {
            id: 'transformer-a',
            kind: 'equipment',
            tag: 'SW A TRANSFORMER',
            system: 'ELEC',
            sourceFileId: 'elec-01',
            page: 1,
            confidence: 0.82,
          },
          {
            id: 'main-breaker',
            kind: 'device',
            tag: 'MAIN BREAKER (SECTION 2)',
            system: 'ELEC',
            sourceFileId: 'elec-01',
            page: 1,
            confidence: 0.78,
          },
          {
            id: 'panel',
            kind: 'line_tag',
            tag: 'RW4MDP4F21',
            system: 'ELEC',
            sourceFileId: 'elec-01',
            page: 1,
            confidence: 0.9,
          },
        ],
        edges: [
          {
            id: 'edge-transformer',
            kind: 'equipment_on_section',
            sourceId: 'transformer-a',
            targetId: 'section-a',
            lineTag: 'SW A (SECTION 1)',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.86,
          },
          {
            id: 'edge-breaker',
            kind: 'device_on_equipment',
            sourceId: 'main-breaker',
            targetId: 'transformer-a',
            lineTag: 'SW A TRANSFORMER',
            system: 'ELEC',
            status: 'inferred',
            confidence: 0.78,
          },
          {
            id: 'edge-panel',
            kind: 'feeds_panel',
            sourceId: 'panel',
            targetId: 'main-breaker',
            lineTag: 'RW4MDP4F21',
            system: 'ELEC',
            status: 'inferred',
            confidence: 0.74,
          },
        ],
      },
    },
  };
}

function createDependencyDrawing(): DrawingDocument {
  return {
    id: 'dependency-test',
    projectId: 'project-test',
    name: 'Dependency test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      electricalRelationshipGraph: createElectricalEquipmentFlowDrawing().visualQa.electricalRelationshipGraph,
      dependencyGraph: {
        metrics: { nodes: 7, edges: 6 },
        qa: {},
        nodes: [
          {
            id: 'dep-pump',
            tag: 'R-CW-P-03',
            kind: 'equipment',
            discipline: 'Mechanical',
            description: 'Condenser water pump',
            sourceFileId: 'mech-source',
            page: 2,
            confidence: 0.88,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'dep-vfd',
            tag: 'VFD-R-CW-P-03',
            kind: 'vfd',
            discipline: 'Electrical',
            description: 'Pump VFD',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.92,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'dep-panel',
            tag: 'RW4PP1E4',
            kind: 'panel',
            discipline: 'Electrical',
            description: 'Power panel',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'dep-mdp',
            tag: 'RW4MDP4C6',
            kind: 'main_distribution_panel',
            discipline: 'Electrical',
            description: 'Main distribution panel',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.95,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'dep-motor',
            tag: 'R-CW-P-03-MTR',
            kind: 'motor',
            discipline: 'Mechanical',
            description: 'Pump motor',
            sourceFileId: 'mech-source',
            page: 2,
            confidence: 0.86,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'dep-bas',
            tag: 'BAS-CP-01',
            kind: 'control_panel',
            discipline: 'Controls / BAS',
            description: 'BAS control panel',
            sourceFileId: 'ic-source',
            page: 3,
            confidence: 0.81,
            metadata: { sourcePath: '/packages/IC Package.pdf' },
          },
          {
            id: 'dep-pit',
            tag: 'PIT-R-CW-P-03',
            kind: 'instrument',
            discipline: 'Instrumentation & Control',
            description: 'Pump discharge pressure transmitter',
            sourceFileId: 'ic-source',
            page: 4,
            confidence: 0.79,
            metadata: { sourcePath: '/packages/IC Package.pdf' },
          },
        ],
        edges: [
          {
            id: 'dep-edge-vfd',
            sourceId: 'dep-vfd',
            targetId: 'dep-pump',
            sourceTag: 'VFD-R-CW-P-03',
            targetTag: 'R-CW-P-03',
            kind: 'requires_drive',
            label: 'requires_drive',
            status: 'inferred',
            confidence: 0.86,
            ruleId: 'dependency.vfd.v1',
            sourceEvidenceIds: ['ev:vfd', 'ev:pump'],
            metadata: {
              sourceDiscipline: 'Electrical',
              targetDiscipline: 'Mechanical',
              dependencyPath: 'R-CW-P-03 <- VFD-R-CW-P-03',
              commissioningUse: 'Pump functional testing requires the VFD to be installed, powered, and ready.',
              evidenceText: 'shared equipment root',
            },
          },
          {
            id: 'dep-edge-panel',
            sourceId: 'dep-panel',
            targetId: 'dep-pump',
            sourceTag: 'RW4PP1E4',
            targetTag: 'R-CW-P-03',
            kind: 'requires_power',
            label: 'requires_power',
            status: 'confirmed',
            confidence: 0.94,
            ruleId: 'dependency.vfd.v1',
            sourceEvidenceIds: ['ev:vfd', 'ev:panel'],
            metadata: {
              sourceDiscipline: 'Electrical',
              targetDiscipline: 'Mechanical',
              dependencyPath: 'R-CW-P-03 <- VFD-R-CW-P-03 <- RW4PP1E4',
              commissioningUse: 'Local panel must be energized before pump run testing.',
              evidenceText: 'panel schedule',
            },
          },
          {
            id: 'dep-edge-mdp',
            sourceId: 'dep-mdp',
            targetId: 'dep-pump',
            sourceTag: 'RW4MDP4C6',
            targetTag: 'R-CW-P-03',
            kind: 'requires_upstream_distribution',
            label: 'requires_upstream_distribution',
            status: 'confirmed',
            confidence: 0.91,
            ruleId: 'dependency.vfd.v1',
            sourceEvidenceIds: ['ev:mdp'],
            metadata: {
              sourceDiscipline: 'Electrical',
              targetDiscipline: 'Mechanical',
              dependencyPath: 'R-CW-P-03 <- VFD-R-CW-P-03 <- RW4PP1E4 <- RW4MDP4C6',
              commissioningUse: 'Upstream distribution must be accepted before downstream pump testing.',
              evidenceText: 'one-line',
            },
          },
          {
            id: 'dep-edge-motor',
            sourceId: 'dep-motor',
            targetId: 'dep-pump',
            sourceTag: 'R-CW-P-03-MTR',
            targetTag: 'R-CW-P-03',
            kind: 'requires_motor',
            label: 'requires_motor',
            status: 'inferred',
            confidence: 0.78,
            ruleId: 'dependency.vfd.v1',
            sourceEvidenceIds: ['ev:motor'],
            metadata: {
              sourceDiscipline: 'Mechanical',
              targetDiscipline: 'Mechanical',
              dependencyPath: 'R-CW-P-03 <- R-CW-P-03-MTR',
              commissioningUse: 'Motor check belongs in the pump start/run chain.',
              evidenceText: 'shared tag root',
            },
          },
          {
            id: 'dep-edge-bas',
            sourceId: 'dep-bas',
            targetId: 'dep-pump',
            sourceTag: 'BAS-CP-01',
            targetTag: 'R-CW-P-03',
            kind: 'requires_control_panel',
            label: 'requires_control_panel',
            status: 'needs_review',
            confidence: 0.62,
            ruleId: 'dependency.vfd.v1',
            sourceEvidenceIds: ['ev:bas'],
            metadata: {
              sourceDiscipline: 'Controls / BAS',
              targetDiscipline: 'Mechanical',
              dependencyPath: 'R-CW-P-03 <- BAS-CP-01',
              commissioningUse: 'BAS panel must be ready for start-stop, alarm, and status checks.',
              evidenceText: 'nearby I&C panel',
            },
          },
          {
            id: 'dep-edge-pit',
            sourceId: 'dep-pit',
            targetId: 'dep-pump',
            sourceTag: 'PIT-R-CW-P-03',
            targetTag: 'R-CW-P-03',
            kind: 'requires_instrument',
            label: 'requires_instrument',
            status: 'needs_review',
            confidence: 0.64,
            ruleId: 'dependency.vfd.v1',
            sourceEvidenceIds: ['ev:pit'],
            metadata: {
              sourceDiscipline: 'Instrumentation & Control',
              targetDiscipline: 'Mechanical',
              dependencyPath: 'R-CW-P-03 <- PIT-R-CW-P-03',
              commissioningUse: 'I&C pressure point supplies proof or feedback during pump testing.',
              evidenceText: 'instrument index',
            },
          },
        ],
      },
    },
  };
}

function createMixedDisciplineDrawing(): DrawingDocument {
  return {
    id: 'mixed-discipline-test',
    projectId: 'project-test',
    name: 'Mixed discipline tree test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      semanticRelationshipGraph: {
        metrics: { nodes: 4, edges: 2 },
        qa: {},
        nodes: [
          {
            id: 'line-cda',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 1,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'compressor',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 1,
            confidence: 0.9,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'elec-duplicate-noise',
            kind: 'equipment',
            tag: 'RW4MDP4F21',
            system: 'DEFAULT',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.7,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'elec-duplicate-line',
            kind: 'line_tag',
            tag: 'RW4MDP4F21',
            system: 'DEFAULT',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.7,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-compressor',
            kind: 'attached_to_line',
            sourceId: 'compressor',
            targetId: 'line-cda',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.9,
          },
          {
            id: 'edge-elec-noise',
            kind: 'attached_to_line',
            sourceId: 'elec-duplicate-noise',
            targetId: 'elec-duplicate-line',
            lineTag: 'RW4MDP4F21',
            system: 'DEFAULT',
            status: 'inferred',
            confidence: 0.7,
          },
        ],
      },
      electricalRelationshipGraph: {
        metrics: { nodes: 4, edges: 3 },
        qa: {},
        nodes: [
          {
            id: 'section-a',
            kind: 'section',
            tag: 'SW A (SECTION 1)',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.88,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'transformer-a',
            kind: 'equipment',
            tag: 'SW A TRANSFORMER',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.82,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'main-breaker',
            kind: 'device',
            tag: 'MAIN BREAKER (SECTION 2)',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.78,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'panel',
            kind: 'line_tag',
            tag: 'RW4MDP4F21',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 1,
            confidence: 0.9,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-transformer',
            kind: 'equipment_on_section',
            sourceId: 'transformer-a',
            targetId: 'section-a',
            lineTag: 'SW A (SECTION 1)',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.86,
          },
          {
            id: 'edge-breaker',
            kind: 'device_on_equipment',
            sourceId: 'main-breaker',
            targetId: 'transformer-a',
            lineTag: 'SW A TRANSFORMER',
            system: 'ELEC',
            status: 'inferred',
            confidence: 0.78,
          },
          {
            id: 'edge-panel',
            kind: 'feeds_panel',
            sourceId: 'panel',
            targetId: 'main-breaker',
            lineTag: 'RW4MDP4F21',
            system: 'ELEC',
            status: 'inferred',
            confidence: 0.74,
          },
        ],
      },
    },
  };
}

function createComponentOnlyDrawing(): DrawingDocument {
  return {
    id: 'component-only-test',
    projectId: 'project-test',
    name: 'Component hierarchy tree test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      semanticRelationshipGraph: {
        metrics: { nodes: 2, edges: 1 },
        qa: {},
        nodes: [
          {
            id: 'fcu',
            kind: 'equipment',
            tag: 'R-SA-FCU-102',
            system: 'SA',
            sourceFileId: 'mech-source',
            page: 1,
            confidence: 0.9,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'tcv',
            kind: 'equipment',
            tag: 'FCU-102-TCV-01',
            system: 'SA',
            sourceFileId: 'mech-source',
            page: 1,
            confidence: 0.82,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-tcv',
            kind: 'equipment_component',
            sourceId: 'tcv',
            targetId: 'fcu',
            lineTag: '',
            system: 'SA',
            status: 'inferred',
            confidence: 0.82,
          },
        ],
      },
    },
  };
}

function createDuplicateTagDrawing(): DrawingDocument {
  return {
    id: 'duplicate-tag-tree-test',
    projectId: 'project-test',
    name: 'Duplicate tag tree test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      semanticRelationshipGraph: {
        metrics: { nodes: 6, edges: 4 },
        qa: {},
        nodes: [
          {
            id: 'line-cda-page-1',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 5,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'line-cda-page-2',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 6,
            confidence: 0.9,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'compressor-page-1',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 5,
            confidence: 0.88,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'compressor-page-2',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 6,
            confidence: 0.92,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'pit-421',
            kind: 'instrument',
            tag: 'PIT-421',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 6,
            confidence: 0.86,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
          {
            id: 'xv-421',
            kind: 'device',
            tag: 'XV-421',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 6,
            confidence: 0.82,
            metadata: { sourcePath: '/packages/Mech Package.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-compressor-page-1',
            kind: 'attached_to_line',
            sourceId: 'compressor-page-1',
            targetId: 'line-cda-page-1',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.88,
          },
          {
            id: 'edge-compressor-page-2',
            kind: 'attached_to_line',
            sourceId: 'compressor-page-2',
            targetId: 'line-cda-page-2',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.92,
          },
          {
            id: 'edge-pit-page-2',
            kind: 'instrument_on_line',
            sourceId: 'pit-421',
            targetId: 'line-cda-page-2',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.86,
          },
          {
            id: 'edge-xv-page-2',
            kind: 'device_on_equipment',
            sourceId: 'xv-421',
            targetId: 'compressor-page-2',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.82,
          },
        ],
      },
    },
  };
}

function createBuildingHierarchyDrawing(): DrawingDocument {
  return {
    id: 'building-hierarchy-test',
    projectId: 'project-test',
    name: 'Building hierarchy tree test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      semanticRelationshipGraph: {
        metrics: { nodes: 2, edges: 1 },
        qa: {},
        nodes: [
          {
            id: 'line-cda',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 5,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf' },
          },
          {
            id: 'compressor',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'mech-source',
            page: 5,
            confidence: 0.88,
            metadata: { sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-compressor',
            kind: 'attached_to_line',
            sourceId: 'compressor',
            targetId: 'line-cda',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.88,
          },
        ],
      },
    },
  };
}

function createDuplicateTagsAcrossBuildingsDrawing(): DrawingDocument {
  return {
    id: 'duplicate-tags-different-buildings-test',
    projectId: 'project-test',
    name: 'Duplicate tags in different buildings test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      semanticRelationshipGraph: {
        metrics: { nodes: 4, edges: 2 },
        qa: {},
        nodes: [
          {
            id: 'line-cda-demo',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'demo-me-source',
            page: 5,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf' },
          },
          {
            id: 'compressor-demo',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'demo-me-source',
            page: 5,
            confidence: 0.88,
            metadata: { sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf' },
          },
          {
            id: 'line-cda-demx',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'demx-me-source',
            page: 5,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/reviewed/DEMX-ME-4CDA01.pdf' },
          },
          {
            id: 'compressor-demx',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'demx-me-source',
            page: 5,
            confidence: 0.88,
            metadata: { sourcePath: '/packages/reviewed/DEMX-ME-4CDA01.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-compressor-demo',
            kind: 'attached_to_line',
            sourceId: 'compressor-demo',
            targetId: 'line-cda-demo',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.88,
          },
          {
            id: 'edge-compressor-demx',
            kind: 'attached_to_line',
            sourceId: 'compressor-demx',
            targetId: 'line-cda-demx',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.88,
          },
        ],
      },
    },
  };
}

function createMixedDisciplinesSameBuildingDrawing(): DrawingDocument {
  return {
    id: 'same-building-mixed-disciplines-test',
    projectId: 'project-test',
    name: 'Same building mixed disciplines test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      semanticRelationshipGraph: {
        metrics: { nodes: 4, edges: 2 },
        qa: {},
        nodes: [
          {
            id: 'line-cda',
            kind: 'line_tag',
            tag: '6"-CDA-CS01',
            system: 'CDA',
            sourceFileId: 'demo-me-source',
            page: 5,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf' },
          },
          {
            id: 'compressor',
            kind: 'equipment',
            tag: 'R-CDA-C-04',
            system: 'CDA',
            sourceFileId: 'demo-me-source',
            page: 5,
            confidence: 0.88,
            metadata: { sourcePath: '/packages/reviewed/DEMO-ME-4CDA01.pdf' },
          },
          {
            id: 'section-elec',
            kind: 'section',
            tag: 'SW A (SECTION 1)',
            system: 'ELEC',
            sourceFileId: 'demo-e-source',
            page: 180,
            confidence: 0.9,
            metadata: { sourcePath: '/packages/reviewed/DEMO-E-401.pdf' },
          },
          {
            id: 'switchgear',
            kind: 'equipment',
            tag: 'RW4SWG2F6',
            system: 'ELEC',
            sourceFileId: 'demo-e-source',
            page: 180,
            confidence: 0.86,
            metadata: { sourcePath: '/packages/reviewed/DEMO-E-401.pdf' },
          },
        ],
        edges: [
          {
            id: 'edge-compressor',
            kind: 'attached_to_line',
            sourceId: 'compressor',
            targetId: 'line-cda',
            lineTag: '6"-CDA-CS01',
            system: 'CDA',
            status: 'inferred',
            confidence: 0.88,
          },
          {
            id: 'edge-switchgear',
            kind: 'equipment_on_section',
            sourceId: 'switchgear',
            targetId: 'section-elec',
            lineTag: 'SW A (SECTION 1)',
            system: 'ELEC',
            status: 'inferred',
            confidence: 0.86,
          },
        ],
      },
    },
  };
}

function createElectricalEquipmentFlowDrawing(): DrawingDocument {
  return {
    id: 'electrical-equipment-flow-test',
    projectId: 'project-test',
    name: 'Electrical equipment flow tree test',
    width: 1200,
    height: 800,
    objects: [],
    sourcePages: [],
    styles: {},
    visualQa: {
      electricalRelationshipGraph: {
        metrics: {
          nodes: 7,
          edges: 6,
          documentGuide: {
            sourcePageIds: ['elec-p1'],
            abbreviations: { GEN: 'GENERATOR', MDP: 'MAIN DISTRIBUTION PANEL', PP: 'POWER PANEL', SS: 'SUBSTATION', SWG: 'SWITCHGEAR' },
            equipmentTagSchema: ['BUILDING', 'POWER SYSTEM', 'VOLTAGE', 'COMPONENT', 'LEVEL', 'GRID LOCATION'],
          },
        },
        qa: {},
        nodes: [
          {
            id: 'upstream-mdp',
            kind: 'line_tag',
            tag: 'RW4MDP4C6',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 182,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'generator',
            kind: 'equipment',
            tag: 'GEN-15',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 180,
            confidence: 0.94,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'switchgear',
            kind: 'line_tag',
            tag: 'RW4SWG2F6',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 180,
            confidence: 0.96,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'compound-target',
            kind: 'line_tag',
            tag: 'RW4SS3D26 & F26',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 180,
            confidence: 0.92,
            metadata: {
              sourcePath: '/packages/Electrical Package.pdf',
              suppressInEquipmentFlow: true,
              resolvedAliasTags: ['RW4SS3D26', 'RW4SS3F26'],
            },
          },
          {
            id: 'substation-d',
            kind: 'line_tag',
            tag: 'RW4SS3D26',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 183,
            confidence: 0.96,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'substation-f',
            kind: 'line_tag',
            tag: 'RW4SS3F26',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 183,
            confidence: 0.96,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'swing-bus',
            kind: 'line_tag',
            tag: "5000A 'SWING' BUS",
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 180,
            confidence: 0.84,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'breaker-52',
            kind: 'device',
            tag: '52',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 180,
            confidence: 0.76,
            metadata: { sourcePath: '/packages/Electrical Package.pdf' },
          },
          {
            id: 'panel-rs2pp1b4',
            kind: 'line_tag',
            tag: 'RS2PP1B4',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 164,
            confidence: 0.94,
            metadata: {
              sourcePath: '/packages/Electrical Package.pdf',
              documentGuideComponent: 'PP',
              documentGuideDescription: 'POWER PANEL',
            },
          },
          {
            id: 'panel-rs2pp1b4-circuit-1',
            kind: 'circuit',
            tag: 'RS2PP1B4 CKT 1',
            system: 'ELEC',
            sourceFileId: 'elec-source',
            page: 164,
            confidence: 0.88,
            metadata: {
              sourcePath: '/packages/Electrical Package.pdf',
              equipmentDescription: 'RECP SUBFAB 204 COL B3',
              circuitNumber: '1',
            },
          },
        ],
        edges: [
          {
            id: 'edge-generator',
            kind: 'power_source',
            sourceId: 'generator',
            targetId: 'upstream-mdp',
            lineTag: 'RW4MDP4C6',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.94,
          },
          {
            id: 'edge-switchgear',
            kind: 'attached_to_line',
            sourceId: 'switchgear',
            targetId: 'generator',
            lineTag: 'GEN-15',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.94,
          },
          {
            id: 'edge-compound',
            kind: 'attached_to_line',
            sourceId: 'compound-target',
            targetId: 'switchgear',
            lineTag: 'RW4SWG2F6',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.92,
          },
          {
            id: 'edge-substation-d',
            kind: 'attached_to_line',
            sourceId: 'substation-d',
            targetId: 'switchgear',
            lineTag: 'RW4SWG2F6',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.92,
          },
          {
            id: 'edge-substation-f',
            kind: 'attached_to_line',
            sourceId: 'substation-f',
            targetId: 'switchgear',
            lineTag: 'RW4SWG2F6',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.92,
          },
          {
            id: 'edge-bus',
            kind: 'attached_to_line',
            sourceId: 'swing-bus',
            targetId: 'switchgear',
            lineTag: 'RW4SWG2F6',
            system: 'ELEC',
            status: 'inferred',
            confidence: 0.84,
          },
          {
            id: 'edge-breaker',
            kind: 'device_on_line',
            sourceId: 'breaker-52',
            targetId: 'switchgear',
            lineTag: 'RW4SWG2F6',
            system: 'ELEC',
            status: 'inferred',
            confidence: 0.76,
          },
          {
            id: 'edge-panel-schedule',
            kind: 'panel_schedule_feeds',
            sourceId: 'panel-rs2pp1b4',
            targetId: 'upstream-mdp',
            lineTag: 'RS2PP1B4',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.92,
          },
          {
            id: 'edge-panel-circuit-1',
            kind: 'panel_circuit',
            sourceId: 'panel-rs2pp1b4-circuit-1',
            targetId: 'panel-rs2pp1b4',
            lineTag: 'RS2PP1B4',
            system: 'ELEC',
            status: 'confirmed',
            confidence: 0.88,
          },
        ],
      },
    },
  };
}
