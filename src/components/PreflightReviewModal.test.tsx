import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { PreflightReviewModal } from './PreflightReviewModal';
import type { HierarchyTemplate, PreflightReview } from '../types';

const review: PreflightReview = {
  projectId: 'project_a',
  status: 'draft',
  disciplines: ['Electrical'],
  disciplineConfidence: 0.91,
  legendPages: [1],
  legendConfidence: 0.87,
  pageRoles: [
    { sourceFileId: 'source_a', page: 1, role: 'legend_reference', confidence: 0.88, reason: 'Legend/reference heading detected.' },
    { sourceFileId: 'source_a', page: 164, role: 'panel_schedule', confidence: 0.88, reason: 'Schedule heading detected.' },
    { sourceFileId: 'source_a', page: 178, role: 'one_line', confidence: 0.78, reason: 'One-line heading detected.' },
  ],
  tableFamilies: ['panel_schedule'],
  suggestedTemplateIds: [],
  appliedTemplateId: null,
  warnings: [],
};

const templates: HierarchyTemplate[] = [
  { id: 'template_a', name: 'Site Electrical', disciplines: ['Electrical'], description: 'Electrical baseline' },
  { id: 'template_b', name: 'Plant P&ID', disciplines: ['Process / P&ID'], description: 'Process baseline' },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('PreflightReviewModal', () => {
  test('renders detected discipline, legend pages, and page roles', () => {
    render(<PreflightReviewModal review={review} onCancel={vi.fn()} onConfirm={vi.fn()} />);

    expect(screen.getByText('Preflight Review')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Electrical')).toBeInTheDocument();
    expect(screen.getByDisplayValue('1')).toBeInTheDocument();
    expect(screen.getByText('panel schedule')).toBeInTheDocument();
    expect(screen.getByText('one line')).toBeInTheDocument();
  });

  test('lets user edit discipline and legend pages before confirmation', () => {
    const onConfirm = vi.fn();
    render(<PreflightReviewModal review={review} onCancel={vi.fn()} onConfirm={onConfirm} />);

    fireEvent.change(screen.getByLabelText('Primary discipline'), { target: { value: 'Process / P&ID' } });
    fireEvent.change(screen.getByLabelText('Legend pages'), { target: { value: '2, 3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Process document' }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        disciplines: ['Process / P&ID'],
        legendPages: [2, 3],
        status: 'confirmed',
      }),
    );
  });

  test('resets editable values when a different review is rendered', () => {
    const onConfirm = vi.fn();
    const nextReview: PreflightReview = {
      ...review,
      projectId: 'project_b',
      disciplines: ['Mechanical'],
      legendPages: [5, 7],
    };
    const { rerender } = render(<PreflightReviewModal review={review} onCancel={vi.fn()} onConfirm={onConfirm} />);

    fireEvent.change(screen.getByLabelText('Primary discipline'), { target: { value: 'Process / P&ID' } });
    fireEvent.change(screen.getByLabelText('Legend pages'), { target: { value: '2, 3' } });
    rerender(<PreflightReviewModal review={nextReview} onCancel={vi.fn()} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole('button', { name: 'Process document' }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: 'project_b',
        disciplines: ['Mechanical'],
        legendPages: [5, 7],
      }),
    );
  });

  test('closes on Escape', () => {
    const onCancel = vi.fn();
    render(<PreflightReviewModal review={review} onCancel={onCancel} onConfirm={vi.fn()} />);

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  test('parses legend pages to sorted unique positive integers', () => {
    const onConfirm = vi.fn();
    render(<PreflightReviewModal review={review} onCancel={vi.fn()} onConfirm={onConfirm} />);

    fireEvent.change(screen.getByLabelText('Legend pages'), { target: { value: '4, 2, 4, 0, -1, abc, 3.5, 1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Process document' }));

    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ legendPages: [1, 2, 4] }));
  });

  test('renders warnings when present', () => {
    render(<PreflightReviewModal review={{ ...review, warnings: ['Low confidence legend match.'] }} onCancel={vi.fn()} onConfirm={vi.fn()} />);

    expect(screen.getByText('Low confidence legend match.')).toBeInTheDocument();
  });

  test('renders only template names listed by suggestedTemplateIds', () => {
    render(
      <PreflightReviewModal
        review={{ ...review, suggestedTemplateIds: ['template_a'] }}
        templates={templates}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    expect(screen.getByText('Suggested templates')).toBeInTheDocument();
    expect(screen.getByText('Site Electrical')).toBeInTheDocument();
    expect(screen.queryByText('Plant P&ID')).not.toBeInTheDocument();
  });

  test('renders suggested templates in ranked review order', () => {
    render(
      <PreflightReviewModal
        review={{ ...review, suggestedTemplateIds: ['template_b', 'template_a'] }}
        templates={templates}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    const suggestedItems = screen.getAllByRole('listitem').map((item) => item.textContent);
    expect(suggestedItems).toEqual(['Plant P&ID', 'Site Electrical']);
  });

  test('does not render template section when no provided templates are suggested', () => {
    render(<PreflightReviewModal review={review} templates={templates} onCancel={vi.fn()} onConfirm={vi.fn()} />);

    expect(screen.queryByText('Suggested templates')).not.toBeInTheDocument();
    expect(screen.queryByText('Site Electrical')).not.toBeInTheDocument();
  });
});
