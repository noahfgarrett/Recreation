import { Check, CheckCheck, CircleAlert, Crosshair, Loader2, X, XCircle } from 'lucide-react';
import { useCallback, useState } from 'react';
import type { ReviewItem } from '../types';

interface ReviewPanelProps {
  items: ReviewItem[];
  onResolve: (item: ReviewItem, resolution: Record<string, unknown>) => Promise<void>;
  onNavigateToNode?: (nodeId: string) => void;
}

export function ReviewPanel({ items, onResolve, onNavigateToNode }: ReviewPanelProps) {
  const openItems = items.filter((item) => item.status === 'open');
  const highConfItems = openItems.filter((item) => {
    const conf = item.candidates[0];
    return conf && typeof conf === 'object' && !('rejected' in conf);
  });
  const resolvedCount = items.filter((item) => item.status === 'resolved').length;
  const [bulkBusy, setBulkBusy] = useState(false);

  const acceptAllHigh = useCallback(async () => {
    setBulkBusy(true);
    try {
      for (const item of highConfItems) {
        await onResolve(item, { accepted: true, candidateIndex: 0, bulk: true });
      }
    } finally {
      setBulkBusy(false);
    }
  }, [highConfItems, onResolve]);

  const rejectAll = useCallback(async () => {
    setBulkBusy(true);
    try {
      for (const item of openItems) {
        await onResolve(item, { accepted: false, rejected: true, bulk: true });
      }
    } finally {
      setBulkBusy(false);
    }
  }, [openItems, onResolve]);

  return (
    <aside className="panel review-panel">
      <div className="panel-heading">
        <h2>Review Queue</h2>
        <span className="count-pill">{openItems.length}</span>
      </div>
      {resolvedCount > 0 ? (
        <p className="muted" style={{ marginTop: 0 }}>
          {resolvedCount} resolved
        </p>
      ) : null}
      {openItems.length > 1 ? (
        <div className="review-bulk-actions">
          <button className="btn-accept-all" onClick={acceptAllHigh} disabled={bulkBusy} title="Accept all with first candidate">
            {bulkBusy ? <Loader2 size={13} className="spin" /> : <CheckCheck size={13} />}
            Accept All
          </button>
          <button className="btn-reject-all" onClick={rejectAll} disabled={bulkBusy} title="Reject all open items">
            {bulkBusy ? <Loader2 size={13} className="spin" /> : <XCircle size={13} />}
            Reject All
          </button>
        </div>
      ) : null}
      <div className="review-list">
        {openItems.length === 0 ? <p className="muted">All review items resolved.</p> : null}
        {openItems.map((item) => (
          <ReviewCard key={item.id} item={item} onResolve={onResolve} onNavigateToNode={onNavigateToNode} />
        ))}
      </div>
    </aside>
  );
}

function ReviewCard({
  item,
  onResolve,
  onNavigateToNode,
}: {
  item: ReviewItem;
  onResolve: (item: ReviewItem, resolution: Record<string, unknown>) => Promise<void>;
  onNavigateToNode?: (nodeId: string) => void;
}) {
  const [activeCandidateIndex, setActiveCandidateIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const hasMultipleCandidates = item.candidates.length > 1;
  const activeCandidate = item.candidates[activeCandidateIndex] ?? {};
  const relatedNodeId = extractNodeId(item);

  const handleResolve = useCallback(
    async (resolution: Record<string, unknown>) => {
      if (busy) return;
      setBusy(true);
      try {
        await onResolve(item, resolution);
      } finally {
        setBusy(false);
      }
    },
    [busy, item, onResolve],
  );

  return (
    <article className="review-item">
      <header>
        <CircleAlert size={14} />
        <strong>{labelForType(item.type)}</strong>
        {relatedNodeId && onNavigateToNode ? (
          <button
            className="review-locate-btn"
            onClick={() => onNavigateToNode(relatedNodeId)}
            title="Locate on canvas"
          >
            <Crosshair size={13} />
          </button>
        ) : null}
        <span className="review-badge">{item.status}</span>
      </header>
      <p>{item.recommendedAction}</p>

      {hasMultipleCandidates ? (
        <div className="candidate-tabs">
          {item.candidates.map((_, index) => (
            <button
              key={index}
              className={`candidate-tab${index === activeCandidateIndex ? ' candidate-tab--active' : ''}`}
              onClick={() => setActiveCandidateIndex(index)}
            >
              Option {index + 1}
            </button>
          ))}
        </div>
      ) : null}

      <dl className="candidate-list">
        {Object.entries(activeCandidate).map(([key, value]) => (
          <div key={key}>
            <dt>{labelForKey(key)}</dt>
            <dd>{String(value)}</dd>
          </div>
        ))}
      </dl>

      <div className="review-actions">
        <button
          className="btn-accept"
          disabled={busy}
          onClick={() => handleResolve({ accepted: true, candidateIndex: activeCandidateIndex })}
        >
          {busy ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
          Accept
        </button>
        <button
          className="btn-reject"
          disabled={busy}
          onClick={() => handleResolve({ accepted: false, rejected: true })}
        >
          <X size={14} />
          Reject
        </button>
      </div>
    </article>
  );
}

function labelForKey(key: string): string {
  return key
    .replace(/([A-Z])/g, ' $1')
    .replace(/_/g, ' ')
    .replace(/^./, (char) => char.toUpperCase())
    .trim();
}

function labelForType(type: ReviewItem['type']): string {
  return type
    .split('_')
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');
}

function extractNodeId(item: ReviewItem): string | null {
  for (const candidate of item.candidates) {
    if (typeof candidate.nodeId === 'string') return candidate.nodeId;
    if (typeof candidate.node_id === 'string') return candidate.node_id;
  }
  for (const ev of item.evidence) {
    if (ev.id) return ev.id.split(':')[0];
  }
  return null;
}
