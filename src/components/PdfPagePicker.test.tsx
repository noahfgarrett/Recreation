import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PdfPagePicker, parsePageSelection } from './PdfPagePicker';
import type { PdfPreview } from '../api/client';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('parsePageSelection', () => {
  it('parses comma-separated pages and ranges in document order', () => {
    expect(parsePageSelection('4, 1-3, 3', 5)).toEqual({ pages: [1, 2, 3, 4], error: null });
  });

  it('reports invalid and out-of-range page entries', () => {
    expect(parsePageSelection('1, 7', 4).error).toMatch(/between 1 and 4/);
    expect(parsePageSelection('1, abc', 4).error).toMatch(/Use page numbers/);
  });
});

describe('PdfPagePicker', () => {
  const preview: PdfPreview = {
    path: '/tmp/pkg.pdf',
    name: 'pkg.pdf',
    pageCount: 4,
    pages: [1, 2, 3, 4].map((page) => ({
      page,
      width: 612,
      height: 792,
      thumbnailUrl: `/pdf-preview/page-image?path=%2Ftmp%2Fpkg.pdf&page=${page}&dpi=54`,
    })),
  };

  it('applies a page range by replacing the current thumbnail selection', async () => {
    const onConfirm = vi.fn();
    const api = {
      previewPdf: vi.fn().mockResolvedValue(preview),
      pdfPreviewPageImageUrl: (_path: string, page: number) => `thumb-${page}.webp`,
    };

    render(<PdfPagePicker api={api} paths={['/tmp/pkg.pdf']} onCancel={() => undefined} onConfirm={onConfirm} />);

    expect(await screen.findByText('pkg.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Toggle page 2/i }));
    fireEvent.change(screen.getByLabelText(/Page range/i), { target: { value: '3-4' } });
    fireEvent.click(screen.getByRole('button', { name: /Apply range/i }));
    fireEvent.click(screen.getByRole('button', { name: /Import selected pages/i }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith([{ path: '/tmp/pkg.pdf', pages: [3, 4] }]);
    });
  });

  it('can add a page range into the current thumbnail selection', async () => {
    const onConfirm = vi.fn();
    const api = {
      previewPdf: vi.fn().mockResolvedValue(preview),
      pdfPreviewPageImageUrl: (_path: string, page: number) => `thumb-${page}.webp`,
    };

    render(<PdfPagePicker api={api} paths={['/tmp/pkg.pdf']} onCancel={() => undefined} onConfirm={onConfirm} />);

    expect(await screen.findByText('pkg.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Clear/i }));
    fireEvent.click(screen.getByRole('button', { name: /Toggle page 2/i }));
    fireEvent.change(screen.getByLabelText(/Page range/i), { target: { value: '3-4' } });
    fireEvent.click(screen.getByRole('button', { name: /Add range/i }));
    fireEvent.click(screen.getByRole('button', { name: /Import selected pages/i }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith([{ path: '/tmp/pkg.pdf', pages: [2, 3, 4] }]);
    });
  });

  it('shows all pages as selected and restores all pages after clear', async () => {
    const onConfirm = vi.fn();
    const api = {
      previewPdf: vi.fn().mockResolvedValue(preview),
      pdfPreviewPageImageUrl: (_path: string, page: number) => `thumb-${page}.webp`,
    };

    render(<PdfPagePicker api={api} paths={['/tmp/pkg.pdf']} onCancel={() => undefined} onConfirm={onConfirm} />);

    expect(await screen.findByRole('button', { name: /Toggle page 1/i })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('button', { name: /Clear/i }));
    expect(screen.getByRole('button', { name: /Toggle page 1/i })).toHaveAttribute('aria-selected', 'false');

    fireEvent.click(screen.getByRole('button', { name: /All pages/i }));
    expect(screen.getByRole('button', { name: /Toggle page 4/i })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('button', { name: /Import selected pages/i }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith([{ path: '/tmp/pkg.pdf' }]);
    });
  });

  it('supports command/control toggles and shift-click page ranges', async () => {
    const onConfirm = vi.fn();
    const api = {
      previewPdf: vi.fn().mockResolvedValue(preview),
      pdfPreviewPageImageUrl: (_path: string, page: number) => `thumb-${page}.webp`,
    };

    render(<PdfPagePicker api={api} paths={['/tmp/pkg.pdf']} onCancel={() => undefined} onConfirm={onConfirm} />);

    expect(await screen.findByText('pkg.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Clear/i }));
    fireEvent.click(screen.getByRole('button', { name: /Toggle page 1/i }));
    fireEvent.click(screen.getByRole('button', { name: /Toggle page 3/i }), { metaKey: true });
    fireEvent.click(screen.getByRole('button', { name: /Toggle page 4/i }), { shiftKey: true });
    fireEvent.click(screen.getByRole('button', { name: /Import selected pages/i }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith([{ path: '/tmp/pkg.pdf', pages: [3, 4] }]);
    });
  });

  it('supports marquee selection across thumbnails', async () => {
    const onConfirm = vi.fn();
    const api = {
      previewPdf: vi.fn().mockResolvedValue(preview),
      pdfPreviewPageImageUrl: (_path: string, page: number) => `thumb-${page}.webp`,
    };

    render(<PdfPagePicker api={api} paths={['/tmp/pkg.pdf']} onCancel={() => undefined} onConfirm={onConfirm} />);

    expect(await screen.findByText('pkg.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Clear/i }));
    const grid = screen.getByTestId('pdf-page-grid-/tmp/pkg.pdf');
    const page1 = screen.getByRole('button', { name: /Toggle page 1/i });
    const page2 = screen.getByRole('button', { name: /Toggle page 2/i });
    const page4 = screen.getByRole('button', { name: /Toggle page 4/i });
    vi.spyOn(page1, 'getBoundingClientRect').mockReturnValue(rect(20, 20, 80, 80));
    vi.spyOn(page2, 'getBoundingClientRect').mockReturnValue(rect(120, 20, 180, 80));
    vi.spyOn(page4, 'getBoundingClientRect').mockReturnValue(rect(320, 20, 380, 80));

    fireEvent.mouseDown(grid, { button: 0, clientX: 10, clientY: 10 });
    fireEvent.mouseMove(grid, { clientX: 210, clientY: 100 });
    fireEvent.mouseUp(grid);

    expect(page1).toHaveAttribute('aria-selected', 'true');
    expect(page2).toHaveAttribute('aria-selected', 'true');
    expect(page4).toHaveAttribute('aria-selected', 'false');
  });
});

function rect(left: number, top: number, right: number, bottom: number): DOMRect {
  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
    x: left,
    y: top,
    toJSON: () => ({}),
  };
}
