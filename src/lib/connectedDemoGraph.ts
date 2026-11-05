import type { DrawingGraph, EdgeKind, GraphEdge, GraphNode, NodeKind, Project, ReviewItem, SourceEvidence } from '../types';

export const connectedDemoProject: Project = {
  id: 'demo-connected-pids',
  name: 'Demo - Connected P&ID Package',
  createdAt: '2026-05-08T00:00:00.000Z',
  updatedAt: '2026-05-08T00:00:00.000Z',
};

const sourceNameByPage: Record<number, string> = {
  16: 'PID-016 Steam and Condensate.pdf',
  17: 'PID-017 Separator Package.pdf',
  18: 'PID-018 Condensate Recovery.pdf',
  21: 'PID-021 Cooling Water Header.pdf',
  22: 'PID-022 Feed System.pdf',
};

function evidence(id: string, page: number, text: string): SourceEvidence {
  return {
    id: `${id}:ev`,
    sourceFileId: sourceNameByPage[page] ?? `PID-${page}`,
    page,
    bounds: {
      page,
      x: 0.18,
      y: 0.22,
      width: 0.08,
      height: 0.05,
    },
    text,
    confidence: 0.94,
  };
}

function ports(id: string): GraphNode['ports'] {
  return [
    { id: `${id}:top`, label: 'top', side: 'top' },
    { id: `${id}:right`, label: 'right', side: 'right' },
    { id: `${id}:bottom`, label: 'bottom', side: 'bottom' },
    { id: `${id}:left`, label: 'left', side: 'left' },
  ];
}

function node(
  id: string,
  kind: NodeKind,
  tag: string,
  page: number,
  x: number,
  y: number,
  width = 178,
  height = 76,
  symbolId: string | null = kind,
): GraphNode {
  return {
    id,
    kind,
    tag,
    symbolId,
    ports: ports(id),
    sourceEvidence: [evidence(id, page, `${tag} on sheet PID-${page}`)],
    confidence: 0.92,
    locked: true,
    layout: { x, y, width, height },
  };
}

function edge(
  id: string,
  kind: EdgeKind,
  source: string,
  target: string,
  label: string,
  sourcePage: number,
  targetPage = sourcePage,
  status: GraphEdge['status'] = 'confirmed',
): GraphEdge {
  return {
    id,
    kind,
    sourcePort: `${source}:right`,
    targetPort: `${target}:left`,
    label,
    lineOrCableId: label,
    waypoints: [],
    continuationRefs: sourcePage === targetPage ? [] : [`PID-${sourcePage}`, `PID-${targetPage}`],
    sourceEvidence: [
      evidence(`${id}:source`, sourcePage, `${label} leaves PID-${sourcePage}`),
      evidence(`${id}:target`, targetPage, `${label} resumes on PID-${targetPage}`),
    ],
    confidence: status === 'inferred' ? 0.86 : 0.95,
    status,
  };
}

function resolvedReview(id: string, from: string, to: string, page: number): ReviewItem {
  return {
    id,
    type: 'continuation_match',
    candidates: [{ from, to, confidence: 'high' }],
    recommendedAction: `Matched ${from} to ${to}.`,
    evidence: [evidence(id, page, `${from} continuation resolved to ${to}`)],
    resolvedBy: 'demo',
    resolution: { accepted: true, candidateIndex: 0 },
    status: 'resolved',
  };
}

export const connectedDemoGraph: DrawingGraph = {
  projectId: connectedDemoProject.id,
  nodes: [
    node('from-steam-016', 'off_page_connector', 'FROM PID-016', 16, -40, -164, 204, 72),
    node('hv-101', 'valve', 'HV-101', 16, 188, -164, 154, 72),
    node('pi-101', 'instrument', 'PI-101', 16, 188, -298, 150, 72),
    node('to-main-017', 'off_page_connector', 'TO PID-017', 16, 394, -164, 186, 72),

    node('from-016', 'off_page_connector', 'FROM PID-016', 17, 606, -164, 204, 72),
    node('sc-01', 'equipment', 'SC-01', 17, 834, -22, 174, 88),
    node('sp-01', 'equipment', 'SP-01', 17, 1054, -164, 196, 118),
    node('lt-011', 'instrument', 'LT-011', 17, 1054, -330, 148, 72),
    node('mk-01s', 'motor', 'MK-01 S', 17, 1298, -278, 168, 80),
    node('mk-01a', 'motor', 'MK-01 A', 17, 1298, -58, 168, 80),
    node('sc-02', 'equipment', 'SC-02', 17, 1534, -164, 174, 98),

    node('to-cond-018', 'off_page_connector', 'TO PID-018', 18, 1742, -164, 192, 72),
    node('from-cond-018', 'off_page_connector', 'FROM PID-018', 18, 1960, -164, 210, 72),
    node('tk-18', 'equipment', 'TK-18', 18, 2194, -164, 172, 86),
    node('mp-02s', 'motor', 'MP-02 S', 18, 2410, -280, 164, 80),
    node('mp-02a', 'motor', 'MP-02 A', 18, 2410, -50, 164, 80),

    node('to-water-021', 'off_page_connector', 'TO PID-021', 21, 1742, 110, 192, 72),
    node('from-water-021', 'off_page_connector', 'FROM PID-021', 21, 1960, 110, 210, 72),
    node('cw-header', 'equipment', 'CW HEADER', 21, 2194, 110, 192, 76),
    node('fv-021', 'valve', 'FV-021', 21, 2420, 110, 154, 72),

    node('from-feed-022', 'off_page_connector', 'FROM PID-022', 22, 606, 244, 204, 72),
    node('fv-022', 'valve', 'FV-022', 22, 834, 244, 154, 72),
    node('tie-017', 'junction_box', 'TIE-IN 017', 17, 1054, 244, 172, 76),
    node('to-feed-017', 'off_page_connector', 'TO PID-017', 22, 1298, 244, 184, 72),
  ],
  edges: [
    edge('e-steam-valve', 'pipe', 'from-steam-016', 'hv-101', '50-ST-001-HC', 16),
    edge('e-pi-valve', 'instrument_signal', 'pi-101', 'hv-101', 'PT SIGNAL', 16),
    edge('e-valve-to-main', 'continuation', 'hv-101', 'to-main-017', '50-ST-001-HC', 16, 17),
    edge('e-main-from-016', 'continuation', 'to-main-017', 'from-016', '50-ST-001-HC', 16, 17),
    edge('e-from-sc01', 'pipe', 'from-016', 'sc-01', '50-ST-001-HC', 17),
    edge('e-sc01-sp01', 'pipe', 'sc-01', 'sp-01', '50-ST-001-HC', 17),
    edge('e-lt-sp01', 'instrument_signal', 'lt-011', 'sp-01', 'LEVEL', 17),
    edge('e-sp-mk01s', 'pipe', 'sp-01', 'mk-01s', '25-PC-017-NI', 17),
    edge('e-sp-mk01a', 'pipe', 'sp-01', 'mk-01a', '25-PC-017-NI', 17),
    edge('e-mk01s-sc02', 'pipe', 'mk-01s', 'sc-02', '50-PC-017-NI', 17),
    edge('e-mk01a-sc02', 'pipe', 'mk-01a', 'sc-02', '50-PC-017-NI', 17),
    edge('e-sc02-cond', 'continuation', 'sc-02', 'to-cond-018', 'CONDENSATE', 17, 18),
    edge('e-cond-page', 'continuation', 'to-cond-018', 'from-cond-018', 'CONDENSATE', 17, 18),
    edge('e-cond-tank', 'pipe', 'from-cond-018', 'tk-18', '50-PC-018-NI', 18),
    edge('e-tk-pump-s', 'pipe', 'tk-18', 'mp-02s', '25-PC-018-NI', 18),
    edge('e-tk-pump-a', 'pipe', 'tk-18', 'mp-02a', '25-PC-018-NI', 18),
    edge('e-sc02-water', 'continuation', 'sc-02', 'to-water-021', 'COOLING WATER', 17, 21),
    edge('e-water-page', 'continuation', 'to-water-021', 'from-water-021', 'COOLING WATER', 17, 21),
    edge('e-water-header', 'pipe', 'from-water-021', 'cw-header', '25-CW-021-HC', 21),
    edge('e-header-valve', 'pipe', 'cw-header', 'fv-021', '25-CW-021-HC', 21),
    edge('e-feed-in', 'continuation', 'from-feed-022', 'fv-022', 'FEED RETURN', 22, 17),
    edge('e-feed-tie', 'pipe', 'fv-022', 'tie-017', '25-FD-022-HC', 22),
    edge('e-tie-main', 'continuation', 'tie-017', 'to-feed-017', '25-FD-022-HC', 17, 22),
    edge('e-feed-to-sp', 'pipe', 'to-feed-017', 'sp-01', '25-FD-022-HC', 22, 17),
  ],
  reviewItems: [
    resolvedReview('rv-016-017', 'PID-016 edge exit', 'PID-017 source', 17),
    resolvedReview('rv-017-018', 'PID-017 condensate arrow', 'PID-018 recovery', 18),
    resolvedReview('rv-017-021', 'PID-017 cooling water arrow', 'PID-021 header', 21),
    resolvedReview('rv-022-017', 'PID-022 feed return', 'PID-017 tie-in', 22),
  ],
};
