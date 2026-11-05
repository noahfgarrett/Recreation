import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Bounds, SourceEvidence } from '../types';

export interface SourceViewerTarget {
  sourceFileId: string;
  sourceFileName: string;
  page: number;
  totalPages: number;
  bounds: Bounds | null;
  /** All evidence items on this same source file, for multi-highlight. */
  allEvidence: SourceEvidence[];
}

interface SourceViewerProps {
  target: SourceViewerTarget;
  apiBaseUrl: string;
  projectId: string;
  onClose: () => void;
}

const DPI = 150;
const SCALE_FACTOR = DPI / 72; // Convert PDF points → image pixels

export function SourceViewer({ target, apiBaseUrl, projectId, onClose }: SourceViewerProps) {
  const [page, setPage] = useState(target.page);
  const [zoom, setZoom] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  // Reset page when target changes
  useEffect(() => {
    setPage(target.page);
    setZoom(1);
    setLoading(true);
    setError(null);
  }, [target.page, target.sourceFileId]);

  const imageUrl = `${apiBaseUrl}/projects/${projectId}/sources/${target.sourceFileId}/pages/${page}/image?dpi=${DPI}`;

  const handleImageLoad = useCallback(() => {
    setLoading(false);
    if (imgRef.current) {
      setPageSize({ width: imgRef.current.naturalWidth, height: imgRef.current.naturalHeight });
    }
    // Scroll to the bounds region after rendering
    requestAnimationFrame(() => {
      if (target.bounds && target.bounds.page === page && containerRef.current && imgRef.current) {
        const bx = target.bounds.x * SCALE_FACTOR * zoom;
        const by = target.bounds.y * SCALE_FACTOR * zoom;
        const container = containerRef.current;
        container.scrollTo({
          left: bx - container.clientWidth / 2,
          top: by - container.clientHeight / 2,
          behavior: 'smooth',
        });
      }
    });
  }, [target.bounds, page, zoom]);

  const handleImageError = useCallback(() => {
    setLoading(false);
    setError('Failed to load page image. The source PDF may have been moved or deleted.');
  }, []);

  // Keyboard navigation
  useEffect(() => {
    function handleKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'ArrowLeft' && page > 1) {
        setPage((p) => p - 1);
        setLoading(true);
      } else if (e.key === 'ArrowRight' && page < target.totalPages) {
        setPage((p) => p + 1);
        setLoading(true);
      } else if (e.key === '+' || e.key === '=') {
        setZoom((z) => Math.min(z + 0.25, 3));
      } else if (e.key === '-') {
        setZoom((z) => Math.max(z - 0.25, 0.25));
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose, page, target.totalPages]);

  // Collect evidence bounds on the current page for highlighting
  const boundsOnPage = target.allEvidence
    .filter((ev) => ev.page === page && ev.bounds !== null)
    .map((ev) => ev.bounds as Bounds);

  // If the primary target bounds is on this page, make sure it's included
  const primaryBounds = target.bounds?.page === page ? target.bounds : null;

  return (
    <div className="source-viewer-backdrop" onClick={onClose}>
      <div className="source-viewer" onClick={(e) => e.stopPropagation()}>
        <div className="source-viewer__header">
          <div className="source-viewer__title">
            <strong>{target.sourceFileName}</strong>
            <span className="source-viewer__page-info">
              Page {page} of {target.totalPages}
            </span>
          </div>
          <div className="source-viewer__controls">
            <button
              title="Previous page"
              disabled={page <= 1}
              onClick={() => { setPage((p) => p - 1); setLoading(true); }}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              title="Next page"
              disabled={page >= target.totalPages}
              onClick={() => { setPage((p) => p + 1); setLoading(true); }}
            >
              <ChevronRight size={16} />
            </button>
            <span className="source-viewer__divider" />
            <button title="Zoom out" onClick={() => setZoom((z) => Math.max(z - 0.25, 0.25))}>
              <ZoomOut size={16} />
            </button>
            <span className="source-viewer__zoom-label">{Math.round(zoom * 100)}%</span>
            <button title="Zoom in" onClick={() => setZoom((z) => Math.min(z + 0.25, 3))}>
              <ZoomIn size={16} />
            </button>
            <span className="source-viewer__divider" />
            <button title="Close (Esc)" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="source-viewer__body" ref={containerRef}>
          {loading ? (
            <div className="source-viewer__loading">Loading page...</div>
          ) : null}
          {error ? (
            <div className="source-viewer__error">{error}</div>
          ) : (
            <div
              className="source-viewer__page"
              style={{
                width: pageSize ? pageSize.width * zoom : undefined,
                height: pageSize ? pageSize.height * zoom : undefined,
                position: 'relative',
              }}
            >
              <img
                ref={imgRef}
                src={imageUrl}
                alt={`Page ${page}`}
                onLoad={handleImageLoad}
                onError={handleImageError}
                draggable={false}
                style={{
                  width: pageSize ? pageSize.width * zoom : undefined,
                  height: pageSize ? pageSize.height * zoom : undefined,
                  display: loading ? 'none' : 'block',
                }}
              />
              {!loading && pageSize
                ? boundsOnPage.map((b, i) => (
                    <div
                      key={i}
                      className={`source-viewer__highlight${primaryBounds && b.x === primaryBounds.x && b.y === primaryBounds.y ? ' source-viewer__highlight--primary' : ''}`}
                      style={{
                        left: b.x * SCALE_FACTOR * zoom,
                        top: b.y * SCALE_FACTOR * zoom,
                        width: b.width * SCALE_FACTOR * zoom,
                        height: b.height * SCALE_FACTOR * zoom,
                      }}
                    />
                  ))
                : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
