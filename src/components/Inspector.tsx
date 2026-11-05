import { Check, ExternalLink, FileSearch, Lock, Pencil, Unlock, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { DrawingGraph, NodeKind, SourceEvidence } from '../types';
import { PidSymbol } from './PidSymbols';

interface InspectorProps {
  graph: DrawingGraph;
  selectedId: string | null;
  onToggleLock: (nodeId: string) => void;
  onOpenEvidence: (evidence: SourceEvidence, allEvidence: SourceEvidence[]) => void;
  onUpdateNode?: (nodeId: string, updates: { tag?: string; kind?: NodeKind }) => void;
  onUpdateEdge?: (edgeId: string, updates: { label?: string; lineOrCableId?: string }) => void;
}

function confidenceLabel(confidence: number): string {
  if (confidence >= 0.85) return 'High';
  if (confidence >= 0.6) return 'Medium';
  return 'Low';
}

export function Inspector({ graph, selectedId, onToggleLock, onOpenEvidence, onUpdateNode, onUpdateEdge }: InspectorProps) {
  const node = graph.nodes.find((item) => item.id === selectedId);
  const edge = graph.edges.find((item) => item.id === selectedId);

  if (!node && !edge) {
    return (
      <aside className="panel inspector">
        <h2>Inspector</h2>
        <p className="muted">Select a symbol or connection to view source evidence and properties.</p>
      </aside>
    );
  }

  if (node) {
    return (
      <aside className="panel inspector">
        <div className="panel-heading">
          <h2>Node</h2>
          <button title={node.locked ? 'Unlock position' : 'Lock position'} onClick={() => onToggleLock(node.id)}>
            {node.locked ? <Lock size={15} /> : <Unlock size={15} />}
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <PidSymbol kind={node.kind} symbolId={node.symbolId} size={36} />
          <div>
            <EditableField
              value={node.tag}
              mono
              onSave={(value) => onUpdateNode?.(node.id, { tag: value })}
            />
            <div style={{ fontSize: 11, color: 'var(--rec-text-muted)', marginTop: 2 }}>
              {node.symbolId ?? node.kind.replace(/_/g, ' ')}
            </div>
          </div>
        </div>
        <dl>
          <dt>Kind</dt>
          <dd>{node.kind.replace(/_/g, ' ')}</dd>
          <dt>Symbol</dt>
          <dd>{node.symbolId ?? 'Unclassified'}</dd>
          <dt>Confidence</dt>
          <dd>
            {Math.round(node.confidence * 100)}% ({confidenceLabel(node.confidence)})
          </dd>
          <dt>Position</dt>
          <dd>
            {Math.round(node.layout.x)}, {Math.round(node.layout.y)}
          </dd>
          {node.sourceEvidence[0]?.page ? (
            <>
              <dt>Sheet</dt>
              <dd>{node.sourceEvidence[0].page}</dd>
            </>
          ) : null}
        </dl>
        {node.sourceEvidence.length > 0 ? (
          <button
            className="btn-view-source"
            onClick={() => onOpenEvidence(node.sourceEvidence[0], node.sourceEvidence)}
          >
            <FileSearch size={14} />
            View Source PDF
          </button>
        ) : null}
        <EvidenceList evidence={node.sourceEvidence} onOpenEvidence={(ev) => onOpenEvidence(ev, node.sourceEvidence)} />
      </aside>
    );
  }

  return (
    <aside className="panel inspector">
      <h2>Connection</h2>
      <div style={{ marginBottom: 14 }}>
        <EditableField
          value={edge?.label ?? ''}
          mono
          onSave={edge ? (value) => onUpdateEdge?.(edge.id, { label: value }) : undefined}
        />
      </div>
      <dl>
        <dt>Kind</dt>
        <dd>{edge?.kind.replace(/_/g, ' ')}</dd>
        <dt>Status</dt>
        <dd>{edge?.status.replace(/_/g, ' ')}</dd>
        <dt>Confidence</dt>
        <dd>
          {Math.round((edge?.confidence ?? 0) * 100)}% ({confidenceLabel(edge?.confidence ?? 0)})
        </dd>
        <dt>Line ID</dt>
        <dd>
          <EditableField
            value={edge?.lineOrCableId ?? ''}
            mono
            onSave={edge ? (value) => onUpdateEdge?.(edge.id, { lineOrCableId: value }) : undefined}
          />
        </dd>
      </dl>
      {(edge?.sourceEvidence.length ?? 0) > 0 ? (
        <button
          className="btn-view-source"
          onClick={() => onOpenEvidence(edge!.sourceEvidence[0], edge!.sourceEvidence)}
        >
          <FileSearch size={14} />
          View Source PDF
        </button>
      ) : null}
      <EvidenceList evidence={edge?.sourceEvidence ?? []} onOpenEvidence={(ev) => onOpenEvidence(ev, edge?.sourceEvidence ?? [])} />
    </aside>
  );
}

function EditableField({
  value,
  mono,
  onSave,
}: {
  value: string;
  mono?: boolean;
  onSave?: (value: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDraft(value);
    setIsEditing(false);
  }, [value]);

  useEffect(() => {
    if (isEditing) inputRef.current?.focus();
  }, [isEditing]);

  const commit = useCallback(() => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== value) {
      onSave?.(trimmed);
    }
    setIsEditing(false);
  }, [draft, value, onSave]);

  if (isEditing) {
    return (
      <div className="editable-field editable-field--editing">
        <input
          ref={inputRef}
          className="editable-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setIsEditing(false);
          }}
          onBlur={commit}
          style={mono ? { fontFamily: 'var(--rec-font-mono)' } : undefined}
        />
        <button className="editable-btn" onClick={commit} title="Save">
          <Check size={13} />
        </button>
        <button className="editable-btn" onClick={() => setIsEditing(false)} title="Cancel">
          <X size={13} />
        </button>
      </div>
    );
  }

  return (
    <div className="editable-field">
      <strong style={mono ? { fontSize: 16, fontFamily: 'var(--rec-font-mono)' } : undefined}>{value}</strong>
      {onSave ? (
        <button className="editable-btn" onClick={() => setIsEditing(true)} title="Edit">
          <Pencil size={12} />
        </button>
      ) : null}
    </div>
  );
}

function EvidenceList({
  evidence,
  onOpenEvidence,
}: {
  evidence: SourceEvidence[];
  onOpenEvidence: (evidence: SourceEvidence) => void;
}) {
  return (
    <div className="evidence-list">
      <h3>Source Evidence</h3>
      {evidence.length === 0 ? <p className="muted">No source evidence available.</p> : null}
      {evidence.map((item) => (
        <button key={item.id} className="evidence-row" onClick={() => onOpenEvidence(item)}>
          <span>{item.text}</span>
          <small>p.{item.page}</small>
          <ExternalLink size={13} />
        </button>
      ))}
    </div>
  );
}
