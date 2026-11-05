import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import ELK from 'elkjs/lib/elk.bundled.js';
import { GitBranch, LayoutGrid, Lock, Minimize2, Maximize2, Save, Trash2, Unlock } from 'lucide-react';
import type { DrawingGraph, NodeKind } from '../types';
import {
  applyFlowPositions,
  matchesSearchFilter,
  toFlowEdges,
  toFlowNodes,
  type PidEdgeData,
  type PidNodeData,
  type SearchFilter,
} from '../lib/graphAdapters';
import { PidEdge } from './PidEdge';
import { PidNode } from './PidNode';

const nodeTypes = { pidNode: PidNode };
const edgeTypes = { pidEdge: PidEdge };
const elk = new ELK();

export type FocusNodeFn = (nodeId: string) => void;

interface CanvasProps {
  graph: DrawingGraph;
  onGraphChange: (graph: DrawingGraph) => void;
  onSaveLayout: (graph: DrawingGraph) => Promise<void>;
  onSelectElement: (id: string | null) => void;
  onNodeContextMenu?: (nodeId: string, x: number, y: number) => void;
  onBulkLock?: (nodeIds: string[], lock: boolean) => void;
  onBulkDelete?: (nodeIds: string[]) => void;
  onBulkSetKind?: (nodeIds: string[], kind: NodeKind) => void;
  onReady?: (focusNode: FocusNodeFn) => void;
  searchFilter?: SearchFilter;
  theme: 'light' | 'dark';
}

export function Canvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

function CanvasInner({ graph, onGraphChange, onSaveLayout, onSelectElement, onNodeContextMenu, onBulkLock, onBulkDelete, searchFilter, theme, onReady }: CanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node<PidNodeData>[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge<PidEdgeData>[]);
  const [compact, setCompact] = useState(false);
  const autoLayoutKey = useRef<string | null>(null);
  const readyRef = useRef(false);
  const lastSyncedGraphRef = useRef<string>('');
  const { fitView } = useReactFlow();
  const fitPadding = graph.projectId === 'demo-connected-pids' ? 0.08 : 0.2;

  useEffect(() => {
    if (!readyRef.current && onReady) {
      readyRef.current = true;
      onReady((nodeId: string) => {
        onSelectElement(nodeId);
        fitView({ nodes: [{ id: nodeId }], padding: 0.5, duration: 400 });
      });
    }
  }, [fitView, onSelectElement, onReady]);

  useEffect(() => {
    const graphKey = `${graph.projectId}:${graph.nodes.length}:${graph.edges.length}:${graph.nodes.map((n) => n.id).join(',')}`;
    if (lastSyncedGraphRef.current === graphKey) {
      return;
    }
    lastSyncedGraphRef.current = graphKey;

    const nextNodes = toFlowNodes(graph.nodes, searchFilter);
    const nextEdges = toFlowEdges(graph.edges);

    const raf = requestAnimationFrame(() => {
      setNodes(nextNodes);
      setEdges(nextEdges);

      const layoutKey = `${graph.projectId}:${graph.nodes.length}:${graph.edges.length}`;
      if (graph.nodes.length > 3 && autoLayoutKey.current !== layoutKey) {
        autoLayoutKey.current = layoutKey;
        window.setTimeout(async () => {
          const layoutedNodes = await calculateLayout(nextNodes, nextEdges, compact);
          setNodes(layoutedNodes);
          onGraphChange(applyFlowPositions(graph, layoutedNodes));
          window.setTimeout(() => fitView({ padding: fitPadding, duration: 300 }), 40);
        }, 80);
      }
    });

    return () => cancelAnimationFrame(raf);
  }, [fitPadding, fitView, graph.projectId, graph.nodes, graph.edges, onGraphChange, setNodes, setEdges, compact]);

  useEffect(() => {
    const matchingIds: string[] = [];
    setNodes((current) =>
      current.map((node) => {
        const graphNode = graph.nodes.find((gn) => gn.id === node.id);
        if (!graphNode) return node;
        const nextMatch = matchesSearchFilter(graphNode, searchFilter);
        if (nextMatch) matchingIds.push(node.id);
        if (node.data.searchMatch === nextMatch) return node;
        return { ...node, data: { ...node.data, searchMatch: nextMatch } };
      }),
    );
    if (searchFilter && (searchFilter.query.length > 0 || searchFilter.kind !== null || searchFilter.confidence !== null) && matchingIds.length > 0 && matchingIds.length < graph.nodes.length) {
      window.setTimeout(() => {
        fitView({ nodes: matchingIds.map((id) => ({ id })), padding: 0.3, duration: 350 });
      }, 50);
    }
  }, [searchFilter, graph.nodes, setNodes, fitView]);

  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);

  const commitNodePositions = useCallback(
    (nextNodes: Node[] = nodes) => {
      onGraphChange(applyFlowPositions(graph, nextNodes));
    },
    [graph, nodes, onGraphChange],
  );

  const runLayout = useCallback(async () => {
    const nextNodes = await calculateLayout(nodes, edges, compact);
    setNodes(nextNodes);
    onGraphChange(applyFlowPositions(graph, nextNodes));
    window.setTimeout(() => fitView({ padding: fitPadding, duration: 300 }), 40);
  }, [compact, edges, fitPadding, fitView, graph, nodes, onGraphChange, setNodes]);

  const saveLayout = useCallback(async () => {
    await onSaveLayout(applyFlowPositions(graph, nodes));
  }, [graph, nodes, onSaveLayout]);

  const gridColor = theme === 'dark' ? '#1E2229' : '#D4DCE4';
  const bgColor = theme === 'dark' ? '#111418' : '#F0F4F7';

  return (
    <div className="canvas-shell">
      <div className="canvas-actions" role="toolbar" aria-label="Canvas actions">
        <button title="Auto layout (ELK)" onClick={runLayout}>
          <LayoutGrid size={16} />
        </button>
        <button
          title={compact ? 'Switch to expanded layout' : 'Switch to compact layout'}
          className={compact ? 'canvas-actions__active' : ''}
          onClick={() => {
            const next = !compact;
            setCompact(next);
            window.setTimeout(async () => {
              const nextNodes = await calculateLayout(nodes, edges, next);
              setNodes(nextNodes);
              onGraphChange(applyFlowPositions(graph, nextNodes));
              window.setTimeout(() => fitView({ padding: fitPadding, duration: 300 }), 40);
            }, 20);
          }}
        >
          {compact ? <Maximize2 size={16} /> : <Minimize2 size={16} />}
        </button>
        <button title="Save layout" onClick={saveLayout}>
          <Save size={16} />
        </button>
        <span>
          <GitBranch size={14} />
          {graph.nodes.length} / {graph.edges.length}
        </span>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={(_, __, nextNodes) => commitNodePositions(nextNodes)}
        onSelectionChange={useCallback(({ nodes: sel, edges: selEdges }: { nodes: Node[]; edges: Edge[] }) => {
          const ids = sel.map((n) => n.id);
          setSelectedNodeIds((prev) => {
            if (prev.length === ids.length && prev.every((id, i) => id === ids[i])) return prev;
            return ids;
          });
          onSelectElement(sel[0]?.id ?? selEdges[0]?.id ?? null);
        }, [onSelectElement])}
        onNodeContextMenu={(event, node) => {
          event.preventDefault();
          onNodeContextMenu?.(node.id, event.clientX, event.clientY);
        }}
        fitView
        fitViewOptions={{ padding: fitPadding }}
        snapToGrid
        snapGrid={[16, 16]}
        minZoom={0.05}
        maxZoom={2.5}
        style={{ background: bgColor }}
      >
        <Background gap={24} size={1} color={gridColor} />
        <Controls position="bottom-left" />
        <MiniMap pannable zoomable position="bottom-right" />
      </ReactFlow>
      <CanvasLegend />
      {selectedNodeIds.length > 1 ? (
        <div className="bulk-toolbar" role="toolbar" aria-label="Bulk actions">
          <span className="bulk-toolbar__count">{selectedNodeIds.length} selected</span>
          <button onClick={() => onBulkLock?.(selectedNodeIds, true)} title="Lock all selected">
            <Lock size={14} /> Lock
          </button>
          <button onClick={() => onBulkLock?.(selectedNodeIds, false)} title="Unlock all selected">
            <Unlock size={14} /> Unlock
          </button>
          <button className="bulk-toolbar__danger" onClick={() => onBulkDelete?.(selectedNodeIds)} title="Delete all selected">
            <Trash2 size={14} /> Delete
          </button>
        </div>
      ) : null}
    </div>
  );
}

function CanvasLegend() {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className={`canvas-legend${isOpen ? ' canvas-legend--open' : ''}`}>
      <button className="legend-toggle" onClick={() => setIsOpen((p) => !p)} title={isOpen ? 'Hide legend' : 'Show legend'}>
        {isOpen ? 'Legend' : 'Legend'}
        <span className={`legend-chevron${isOpen ? ' legend-chevron--open' : ''}`} />
      </button>
      {isOpen ? (
        <div className="legend-body">
          <strong className="legend-heading">Process</strong>
          <span className="legend-item legend-item--equipment">Equipment</span>
          <span className="legend-item legend-item--instrument">Instrument</span>
          <span className="legend-item legend-item--valve">Valve</span>
          <span className="legend-item legend-item--panel">Panel</span>
          <span className="legend-item legend-item--junction">J-Box</span>
          <span className="legend-item legend-item--opc">OPC</span>
          <span className="legend-item legend-item--cable">Cable</span>
          <strong className="legend-heading">Electrical</strong>
          <span className="legend-item legend-item--motor">Motor</span>
          <span className="legend-item legend-item--breaker">Breaker</span>
          <span className="legend-item legend-item--transformer">Transformer</span>
          <span className="legend-item legend-item--vfd">VFD</span>
          <span className="legend-item legend-item--mcc">MCC</span>
          <span className="legend-item legend-item--switchgear">Switchgear</span>
        </div>
      ) : null}
    </div>
  );
}

async function calculateLayout(nodes: Node<PidNodeData>[], edges: Edge<PidEdgeData>[], compact = false): Promise<Node<PidNodeData>[]> {
  const locked = new Set(nodes.filter((node) => node.data.locked).map((node) => node.id));
  const layoutGraph = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': compact ? '40' : '140',
      'elk.spacing.nodeNode': compact ? '24' : '80',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: node.width ?? 170,
      height: node.height ?? 88,
    })),
    edges: edges.map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
  };
  const result = await elk.layout(layoutGraph);
  const positions = new Map(
    ((result.children as Array<{ id: string; x?: number; y?: number }>) ?? []).map((node) => [
      node.id,
      { x: node.x ?? 0, y: node.y ?? 0 },
    ]),
  );
  return nodes.map((node) => (locked.has(node.id) ? node : { ...node, position: positions.get(node.id) ?? node.position }));
}
