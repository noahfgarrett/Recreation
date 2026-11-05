import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { DisciplineName, HierarchyTemplate, PageRoleAssignment, PreflightReview } from '../types';

const DISCIPLINES: DisciplineName[] = [
  'Electrical',
  'Process / P&ID',
  'Mechanical',
  'Mechanical Dry',
  'Mechanical Wet',
  'Plumbing',
  'Instrumentation & Control',
  'Security',
  'Fire Alarm',
  'Fire Protection',
  'Life Safety Services',
  'Telecom / Low Voltage',
  'Controls / BAS',
  'CSA',
  'General / Reference',
  'Mixed Package',
  'Unknown',
];

interface PreflightReviewModalProps {
  review: PreflightReview;
  templates?: HierarchyTemplate[];
  onCancel: () => void;
  onConfirm: (review: PreflightReview) => void;
}

export function PreflightReviewModal({ review, templates = [], onCancel, onConfirm }: PreflightReviewModalProps) {
  const reviewDiscipline = review.disciplines[0] ?? 'Unknown';
  const reviewLegendPages = review.legendPages.join(', ');
  const [discipline, setDiscipline] = useState<DisciplineName>(reviewDiscipline);
  const [legendPages, setLegendPages] = useState(reviewLegendPages);
  const dialogRef = useRef<HTMLElement>(null);
  const roleRows = useMemo(() => review.pageRoles.slice().sort((a, b) => a.page - b.page), [review.pageRoles]);
  const suggestedTemplates = useMemo(() => {
    const templatesById = new Map(templates.map((template) => [template.id, template]));
    return review.suggestedTemplateIds
      .map((templateId) => templatesById.get(templateId))
      .filter((template): template is HierarchyTemplate => template !== undefined);
  }, [review.suggestedTemplateIds, templates]);

  useEffect(() => {
    setDiscipline(reviewDiscipline);
    setLegendPages(reviewLegendPages);
  }, [review.projectId, reviewDiscipline, reviewLegendPages]);

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;

    const frame = requestAnimationFrame(() => {
      const firstControl = dialog ? getFocusableControls(dialog)[0] : null;
      (firstControl ?? dialog)?.focus();
    });

    return () => {
      cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  const confirm = () => {
    onConfirm({
      ...review,
      status: 'confirmed',
      disciplines: [discipline],
      legendPages: parsePageList(legendPages),
    });
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onCancel();
      return;
    }

    if (event.key !== 'Tab') {
      return;
    }

    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    const focusableControls = getFocusableControls(dialog);
    if (focusableControls.length === 0) {
      event.preventDefault();
      dialog.focus();
      return;
    }

    const firstControl = focusableControls[0];
    const lastControl = focusableControls[focusableControls.length - 1];
    const activeElement = document.activeElement;

    if (event.shiftKey && activeElement === firstControl) {
      event.preventDefault();
      lastControl.focus();
    } else if (!event.shiftKey && activeElement === lastControl) {
      event.preventDefault();
      firstControl.focus();
    }
  };

  return (
    <div className="preflight-modal-backdrop" role="presentation">
      <section
        ref={dialogRef}
        className="preflight-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preflight-review-title"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <header className="preflight-modal__header">
          <div>
            <h2 id="preflight-review-title">Preflight Review</h2>
            <p>Recreation found the likely discipline, legend pages, and page roles. Adjust them before full extraction.</p>
          </div>
          <button type="button" className="preflight-modal__icon-button" aria-label="Close preflight review" onClick={onCancel}>
            <X size={16} />
          </button>
        </header>

        <div className="preflight-modal__body">
          <div className="preflight-modal__grid">
            <label className="preflight-field-block">
              <span>Primary discipline</span>
              <select value={discipline} onChange={(event) => setDiscipline(event.target.value as DisciplineName)}>
                {DISCIPLINES.map((disciplineName) => (
                  <option key={disciplineName} value={disciplineName}>
                    {disciplineName}
                  </option>
                ))}
              </select>
            </label>

            <label className="preflight-field-block">
              <span>Legend pages</span>
              <input value={legendPages} onChange={(event) => setLegendPages(event.target.value)} inputMode="numeric" />
            </label>
          </div>

          {review.warnings.length > 0 ? (
            <div className="preflight-warning" role="status">
              <AlertTriangle size={16} />
              <div>
                {review.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            </div>
          ) : (
            <div className="preflight-ready" role="status">
              <CheckCircle2 size={16} />
              <span>Ready for extraction</span>
            </div>
          )}

          {suggestedTemplates.length > 0 ? (
            <section className="preflight-template-list" aria-labelledby="preflight-template-list-title">
              <h3 id="preflight-template-list-title">Suggested templates</h3>
              <ul>
                {suggestedTemplates.map((template) => (
                  <li key={template.id}>{template.name}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <div className="preflight-role-table" role="table" aria-label="Detected page roles">
            {roleRows.map((role) => (
              <RoleRow key={`${role.sourceFileId}-${role.page}-${role.role}`} role={role} />
            ))}
          </div>
        </div>

        <footer className="preflight-modal__footer">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={confirm}>
            Process document
          </button>
        </footer>
      </section>
    </div>
  );
}

function RoleRow({ role }: { role: PageRoleAssignment }) {
  return (
    <div className="preflight-role-row" role="row">
      <span className="preflight-role-row__page" role="cell">
        Page {role.page}
      </span>
      <span className="preflight-role-row__role" role="cell">
        {formatRole(role.role)}
      </span>
      <span className="preflight-role-row__confidence" role="cell">
        {Math.round(role.confidence * 100)}%
      </span>
      <span className="preflight-role-row__reason" role="cell">
        {role.reason}
      </span>
    </div>
  );
}

function formatRole(role: string): string {
  return role.replaceAll('_', ' ');
}

function parsePageList(value: string): number[] {
  const pages = value
    .split(',')
    .map((part) => Number(part.trim()))
    .filter((page) => Number.isInteger(page) && page > 0);

  return Array.from(new Set(pages)).sort((a, b) => a - b);
}

function getFocusableControls(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute('hidden') && element.getAttribute('aria-hidden') !== 'true');
}
