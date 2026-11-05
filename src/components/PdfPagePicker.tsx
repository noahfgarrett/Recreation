import { useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent } from 'react';
import { Check, FileText, Images, X } from 'lucide-react';
import type { ImportFileSelection, PdfPreview, RecreationApi } from '../api/client';

interface PdfPagePickerProps {
  api: Pick<RecreationApi, 'previewPdf' | 'pdfPreviewPageImageUrl'>;
  paths: string[];
  onCancel: () => void;
  onConfirm: (files: ImportFileSelection[]) => void;
}

interface PageMarqueeState {
  path: string;
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
  active: boolean;
}

export function parsePageSelection(input: string, pageCount: number): { pages: number[]; error: string | null } {
  const trimmed = input.trim();
  if (!trimmed) return { pages: [], error: null };
  const pages = new Set<number>();

  for (const rawToken of trimmed.split(',')) {
    const token = rawToken.trim();
    if (!token) continue;
    const rangeMatch = token.match(/^(\d+)\s*-\s*(\d+)$/);
    const singleMatch = token.match(/^\d+$/);
    if (rangeMatch) {
      const start = Number(rangeMatch[1]);
      const end = Number(rangeMatch[2]);
      if (start > end) return { pages: [], error: 'Use ascending page ranges like 3-8.' };
      if (start < 1 || end > pageCount) return { pages: [], error: `Pages must be between 1 and ${pageCount}.` };
      for (let page = start; page <= end; page += 1) pages.add(page);
      continue;
    }
    if (singleMatch) {
      const page = Number(token);
      if (page < 1 || page > pageCount) return { pages: [], error: `Pages must be between 1 and ${pageCount}.` };
      pages.add(page);
      continue;
    }
    return { pages: [], error: 'Use page numbers and ranges like 1, 3-6, 9.' };
  }

  return { pages: [...pages].sort((a, b) => a - b), error: null };
}

export function PdfPagePicker({ api, paths, onCancel, onConfirm }: PdfPagePickerProps) {
  const [previews, setPreviews] = useState<PdfPreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPages, setSelectedPages] = useState<Record<string, number[]>>({});
  const [anchorPages, setAnchorPages] = useState<Record<string, number | null>>({});
  const [marquee, setMarquee] = useState<PageMarqueeState | null>(null);
  const [rangeInputs, setRangeInputs] = useState<Record<string, string>>({});
  const [rangeErrors, setRangeErrors] = useState<Record<string, string | null>>({});
  const gridRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const thumbRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all(paths.map((path) => api.previewPdf(path)))
      .then((loaded) => {
        if (cancelled) return;
        setPreviews(loaded);
        setSelectedPages(
          Object.fromEntries(loaded.map((preview) => [preview.path, preview.pages.map((page) => page.page)])),
        );
        setAnchorPages(Object.fromEntries(loaded.map((preview) => [preview.path, null])));
        setLoading(false);
      })
      .catch((nextError) => {
        if (cancelled) return;
        setError(nextError instanceof Error ? nextError.message : 'Could not preview PDF pages');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, paths]);

  const totalSelected = useMemo(() => {
    if (previews.length === 0) return 0;
    return previews.reduce((total, preview) => {
      return total + (selectedPages[preview.path]?.length ?? 0);
    }, 0);
  }, [previews, selectedPages]);

  const setPagesForPath = (path: string, pages: number[]): void => {
    setSelectedPages((current) => ({ ...current, [path]: sortUniquePages(pages) }));
  };

  const handlePageClick = (event: MouseEvent<HTMLButtonElement>, preview: PdfPreview, page: number, pageIndex: number): void => {
    if (marquee?.active) return;
    const current = selectedPages[preview.path] ?? [];
    let nextPages: number[];
    if (event.shiftKey && anchorPages[preview.path]) {
      const anchorIndex = preview.pages.findIndex((candidate) => candidate.page === anchorPages[preview.path]);
      const start = Math.min(anchorIndex >= 0 ? anchorIndex : pageIndex, pageIndex);
      const end = Math.max(anchorIndex >= 0 ? anchorIndex : pageIndex, pageIndex);
      nextPages = preview.pages.slice(start, end + 1).map((candidate) => candidate.page);
    } else if (event.metaKey || event.ctrlKey) {
      const selected = new Set(current);
      if (selected.has(page)) selected.delete(page);
      else selected.add(page);
      nextPages = [...selected];
      setAnchorPages((anchors) => ({ ...anchors, [preview.path]: page }));
    } else {
      nextPages = [page];
      setAnchorPages((anchors) => ({ ...anchors, [preview.path]: page }));
    }
    setPagesForPath(preview.path, nextPages);
  };

  const selectAll = (preview: PdfPreview): void => {
    setPagesForPath(preview.path, preview.pages.map((page) => page.page));
    setAnchorPages((anchors) => ({ ...anchors, [preview.path]: null }));
    setRangeInputs((current) => ({ ...current, [preview.path]: '' }));
    setRangeErrors((current) => ({ ...current, [preview.path]: null }));
  };

  const clearFile = (path: string): void => {
    setPagesForPath(path, []);
    setAnchorPages((anchors) => ({ ...anchors, [path]: null }));
  };

  const applyRange = (preview: PdfPreview, mode: 'replace' | 'add'): void => {
    const parsed = parsePageSelection(rangeInputs[preview.path] ?? '', preview.pageCount);
    setRangeErrors((current) => ({ ...current, [preview.path]: parsed.error }));
    if (parsed.error) return;
    if (mode === 'replace') {
      setPagesForPath(preview.path, parsed.pages);
    } else {
      setSelectedPages((current) => {
        const next = new Set(current[preview.path] ?? []);
        for (const page of parsed.pages) next.add(page);
        return { ...current, [preview.path]: [...next].sort((a, b) => a - b) };
      });
    }
    setAnchorPages((anchors) => ({ ...anchors, [preview.path]: parsed.pages.at(-1) ?? anchors[preview.path] ?? null }));
  };

  const handleGridMouseDown = (event: MouseEvent<HTMLDivElement>, preview: PdfPreview): void => {
    if (event.button !== 0) return;
    setMarquee({
      path: preview.path,
      startX: event.clientX,
      startY: event.clientY,
      currentX: event.clientX,
      currentY: event.clientY,
      active: false,
    });
  };

  const handleGridMouseMove = (event: MouseEvent<HTMLDivElement>, preview: PdfPreview): void => {
    if (!marquee || marquee.path !== preview.path) return;
    const dx = Math.abs(event.clientX - marquee.startX);
    const dy = Math.abs(event.clientY - marquee.startY);
    const nextMarquee = {
      ...marquee,
      currentX: event.clientX,
      currentY: event.clientY,
      active: marquee.active || dx > 6 || dy > 6,
    };
    setMarquee(nextMarquee);
    if (!nextMarquee.active) return;
    const selectionBounds = marqueeBounds(nextMarquee);
    const intersectingPages = preview.pages
      .filter((page) => {
        const element = thumbRefs.current.get(pageKey(preview.path, page.page));
        return element ? rectanglesIntersect(selectionBounds, element.getBoundingClientRect()) : false;
      })
      .map((page) => page.page);
    setPagesForPath(preview.path, intersectingPages);
  };

  const handleGridMouseUp = (): void => {
    if (marquee?.active) {
      const pages = selectedPages[marquee.path] ?? [];
      setAnchorPages((anchors) => ({ ...anchors, [marquee.path]: pages.at(-1) ?? null }));
    }
    setMarquee(null);
  };

  const confirm = (): void => {
    const files = previews
      .map((preview) => {
        const pages = selectedPages[preview.path] ?? [];
        if (pages.length === preview.pageCount) return { path: preview.path };
        return pages.length > 0 ? { path: preview.path, pages } : null;
      })
      .filter((file): file is ImportFileSelection => file !== null);
    onConfirm(files);
  };

  return (
    <div className="project-overlay pdf-page-picker-overlay" onClick={onCancel} role="dialog" aria-label="Select PDF pages">
      <div className="pdf-page-picker" onClick={(event) => event.stopPropagation()}>
        <header className="pdf-page-picker__header">
          <div>
            <h2>Select PDF Pages</h2>
            <p>{loading ? 'Rendering quick WebP thumbnails' : `${totalSelected} page${totalSelected === 1 ? '' : 's'} ready to import`}</p>
          </div>
          <button className="btn-ghost" onClick={onCancel} aria-label="Close page picker">
            <X size={16} />
          </button>
        </header>

        <div className="pdf-page-picker__body">
          {loading ? (
            <div className="pdf-page-picker__empty">
              <Images size={20} />
              Building thumbnail contact sheet
            </div>
          ) : null}
          {error ? <div className="pdf-page-picker__error">{error}</div> : null}
          {!loading && !error
            ? previews.map((preview) => {
                const selected = new Set(selectedPages[preview.path] ?? []);
                const rangeId = `page-range-${preview.path.replace(/[^A-Za-z0-9]/g, '-')}`;
                const fileMarquee = marquee?.path === preview.path ? marquee : null;
                return (
                  <section className="pdf-page-picker__file" key={preview.path}>
                    <div className="pdf-page-picker__file-header">
                      <div>
                        <strong>{preview.name}</strong>
                        <span>
                          {selected.size === preview.pageCount ? `All ${preview.pageCount} pages selected` : `${selected.size} of ${preview.pageCount} selected`}
                        </span>
                      </div>
                      <div className="pdf-page-picker__file-actions">
                        <button onClick={() => selectAll(preview)}>All pages</button>
                        <button onClick={() => clearFile(preview.path)}>Clear</button>
                      </div>
                    </div>
                    <div className="pdf-page-picker__range-row">
                      <label htmlFor={rangeId}>Page range</label>
                      <input
                        id={rangeId}
                        value={rangeInputs[preview.path] ?? ''}
                        placeholder="1, 4-8, 12"
                        onChange={(event) => setRangeInputs((current) => ({ ...current, [preview.path]: event.target.value }))}
                      />
                      <button onClick={() => applyRange(preview, 'replace')}>Apply range</button>
                      <button onClick={() => applyRange(preview, 'add')}>Add range</button>
                    </div>
                    {rangeErrors[preview.path] ? <p className="pdf-page-picker__range-error">{rangeErrors[preview.path]}</p> : null}
                    <div
                      className="pdf-page-picker__thumb-grid"
                      data-testid={`pdf-page-grid-${preview.path}`}
                      ref={(element) => {
                        if (element) gridRefs.current.set(preview.path, element);
                        else gridRefs.current.delete(preview.path);
                      }}
                      onMouseDown={(event) => handleGridMouseDown(event, preview)}
                      onMouseMove={(event) => handleGridMouseMove(event, preview)}
                      onMouseUp={handleGridMouseUp}
                      onMouseLeave={handleGridMouseUp}
                    >
                      {preview.pages.map((page, pageIndex) => {
                        const active = selected.has(page.page);
                        return (
                          <button
                            key={page.page}
                            className={`pdf-page-picker__thumb${active ? ' pdf-page-picker__thumb--selected' : ''}`}
                            onClick={(event) => handlePageClick(event, preview, page.page, pageIndex)}
                            aria-label={`Toggle page ${page.page} of ${preview.name}`}
                            aria-selected={active}
                            ref={(element) => {
                              const key = pageKey(preview.path, page.page);
                              if (element) thumbRefs.current.set(key, element);
                              else thumbRefs.current.delete(key);
                            }}
                          >
                            <img src={api.pdfPreviewPageImageUrl(preview.path, page.page)} alt="" />
                            <span>
                              {active ? <Check size={12} /> : <FileText size={12} />}
                              Page {page.page}
                            </span>
                          </button>
                        );
                      })}
                      {fileMarquee?.active ? <span className="pdf-page-picker__marquee" style={marqueeStyle(fileMarquee, gridRefs.current.get(preview.path) ?? null)} aria-hidden="true" /> : null}
                    </div>
                  </section>
                );
              })
            : null}
        </div>

        <footer className="pdf-page-picker__footer">
          <button className="btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button className="btn-primary" onClick={confirm} disabled={loading || previews.length === 0 || totalSelected === 0}>
            Import selected pages
          </button>
        </footer>
      </div>
    </div>
  );
}

function sortUniquePages(pages: number[]): number[] {
  return [...new Set(pages)].sort((a, b) => a - b);
}

function pageKey(path: string, page: number): string {
  return `${path}::${page}`;
}

function marqueeBounds(marquee: PageMarqueeState): DOMRectLike {
  const left = Math.min(marquee.startX, marquee.currentX);
  const top = Math.min(marquee.startY, marquee.currentY);
  const right = Math.max(marquee.startX, marquee.currentX);
  const bottom = Math.max(marquee.startY, marquee.currentY);
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function marqueeStyle(marquee: PageMarqueeState, container: HTMLElement | null): CSSProperties {
  const bounds = marqueeBounds(marquee);
  const containerBounds = container?.getBoundingClientRect();
  const offsetX = containerBounds?.left ?? 0;
  const offsetY = containerBounds?.top ?? 0;
  return {
    left: bounds.left - offsetX,
    top: bounds.top - offsetY,
    width: bounds.width,
    height: bounds.height,
  };
}

interface DOMRectLike {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

function rectanglesIntersect(left: DOMRectLike, right: DOMRectLike): boolean {
  return left.left <= right.right && left.right >= right.left && left.top <= right.bottom && left.bottom >= right.top;
}
