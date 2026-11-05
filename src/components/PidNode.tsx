import { Handle, NodeResizer, NodeToolbar, Position, type Node, type NodeProps } from '@xyflow/react';
import { Lock } from 'lucide-react';
import type { PidNodeData } from '../lib/graphAdapters';
import { PidSymbol } from './PidSymbols';

type PidFlowNode = Node<PidNodeData, 'pidNode'>;

function confidenceClass(confidence: number): string {
  if (confidence >= 0.75) return 'conf-high';
  if (confidence >= 0.5) return 'conf-mid';
  return 'conf-low';
}

export function PidNode({ id, data, selected }: NodeProps<PidFlowNode>) {
  const dimmed = data.searchMatch === false;

  return (
    <div
      className={`pid-node pid-node--${data.kind}${selected ? ' is-selected' : ''}${dimmed ? ' is-dimmed' : ''}`}
    >
      <NodeResizer isVisible={selected && !data.locked} minWidth={120} minHeight={60} />
      <NodeToolbar isVisible={selected} position={Position.Top} className="node-toolbar">
        <span>{Math.round(data.confidence * 100)}%</span>
        {data.locked ? <Lock size={13} /> : null}
      </NodeToolbar>
      <Handle id={`${id}:top`} type="source" position={Position.Top} className="node-handle" />
      <Handle id={`${id}:left`} type="target" position={Position.Left} className="node-handle" />
      <Handle id={`${id}:right`} type="source" position={Position.Right} className="node-handle" />
      <Handle id={`${id}:bottom`} type="source" position={Position.Bottom} className="node-handle" />
      <div className="pid-node__icon" aria-hidden>
        <PidSymbol kind={data.kind} symbolId={data.symbolId} size={28} />
      </div>
      <div className="pid-node__text">
        <strong>{data.tag}</strong>
        <span>{data.symbolId ?? data.kind.replace(/_/g, ' ')}</span>
      </div>
      {data.page > 0 ? <div className="pid-node__page">Sht {data.page}</div> : null}
      <div className="pid-node__confidence">
        <span
          className={confidenceClass(data.confidence)}
          style={{ width: `${Math.max(8, data.confidence * 100)}%` }}
        />
      </div>
    </div>
  );
}
