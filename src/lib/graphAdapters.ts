import type { Edge, Node, Position } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';
import type { DrawingGraph, GraphEdge, GraphNode, NodeKind } from '../types';

export interface PidNodeData extends Record<string, unknown> {
  tag: string;
  kind: NodeKind;
  symbolId: string | null;
  confidence: number;
  locked: boolean;
  searchMatch: boolean;
  page: number;
}

export interface PidEdgeData extends Record<string, unknown> {
  label: string;
  kind: GraphEdge['kind'];
  confidence: number;
  status: GraphEdge['status'];
}

export type ConfidenceLevel = 'high' | 'medium' | 'low';

export interface SearchFilter {
  query: string;
  kind: NodeKind | null;
  confidence: ConfidenceLevel | null;
  sheet?: number | null;
}

export function toFlowNodes(nodes: GraphNode[], filter?: SearchFilter): Node<PidNodeData>[] {
  return nodes.map((node) => ({
    id: node.id,
    type: 'pidNode',
    position: { x: node.layout.x, y: node.layout.y },
    width: node.layout.width,
    height: node.layout.height,
    draggable: !node.locked,
    sourcePosition: 'right' as Position,
    targetPosition: 'left' as Position,
    data: {
      tag: node.tag,
      kind: node.kind,
      symbolId: node.symbolId,
      confidence: node.confidence,
      locked: node.locked,
      searchMatch: matchesSearchFilter(node, filter),
      page: node.sourceEvidence[0]?.page ?? 0,
    },
  }));
}

export function toFlowEdges(edges: GraphEdge[]): Edge<PidEdgeData>[] {
  return edges.map((edge) => ({
    id: edge.id,
    type: 'pidEdge',
    source: edge.sourcePort.split(':')[0],
    target: edge.targetPort.split(':')[0],
    sourceHandle: edge.sourcePort,
    targetHandle: edge.targetPort,
    markerEnd: { type: MarkerType.ArrowClosed },
    data: {
      label: edge.label,
      kind: edge.kind,
      confidence: edge.confidence,
      status: edge.status,
    },
  }));
}

export function applyFlowPositions(graph: DrawingGraph, nodes: Node[]): DrawingGraph {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return {
    ...graph,
    nodes: graph.nodes.map((node) => {
      const flowNode = byId.get(node.id);
      if (!flowNode) return node;
      return {
        ...node,
        layout: {
          ...node.layout,
          x: flowNode.position.x,
          y: flowNode.position.y,
          width: typeof flowNode.width === 'number' ? flowNode.width : node.layout.width,
          height: typeof flowNode.height === 'number' ? flowNode.height : node.layout.height,
        },
      };
    }),
  };
}

export function openReviewCount(graph: DrawingGraph | null): number {
  return graph?.reviewItems.filter((item) => item.status === 'open').length ?? 0;
}

export function matchesSearchFilter(node: GraphNode, filter?: SearchFilter): boolean {
  if (!filter) return true;
  const hasQuery = filter.query.length > 0;
  const hasKind = filter.kind !== null;
  const hasConfidence = filter.confidence !== null;
  const hasSheet = filter.sheet != null;
  if (!hasQuery && !hasKind && !hasConfidence && !hasSheet) return true;

  if (hasKind && node.kind !== filter.kind) return false;
  if (hasSheet) {
    const nodePage = node.sourceEvidence[0]?.page ?? 0;
    if (nodePage !== filter.sheet) return false;
  }
  if (hasConfidence) {
    if (filter.confidence === 'high' && node.confidence < 0.85) return false;
    if (filter.confidence === 'medium' && (node.confidence < 0.6 || node.confidence >= 0.85)) return false;
    if (filter.confidence === 'low' && node.confidence >= 0.6) return false;
  }
  if (hasQuery) {
    const q = filter.query.toUpperCase();
    return node.tag.toUpperCase().includes(q) || node.kind.toUpperCase().includes(q) || (node.symbolId?.toUpperCase().includes(q) ?? false);
  }
  return true;
}

export function hasActiveFilter(filter?: SearchFilter): boolean {
  if (!filter) return false;
  return filter.query.length > 0 || filter.kind !== null || filter.confidence !== null || (filter.sheet != null);
}
