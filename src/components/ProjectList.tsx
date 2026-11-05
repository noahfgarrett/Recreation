import { FolderOpen, Plus, X } from 'lucide-react';
import type { Project } from '../types';

interface ProjectListProps {
  projects: Project[];
  currentProjectId: string | null;
  onSelect: (project: Project) => void;
  onNew: () => void;
  onClose: () => void;
}

export function ProjectList({ projects, currentProjectId, onSelect, onNew, onClose }: ProjectListProps) {
  return (
    <div className="project-overlay" onClick={onClose} role="dialog" aria-label="Project list">
      <div className="project-dialog" onClick={(e) => e.stopPropagation()}>
        <header className="project-dialog-header">
          <h2>Projects</h2>
          <div className="project-dialog-actions">
            <button className="btn-primary" onClick={onNew}>
              <Plus size={15} />
              Import New
            </button>
            <button className="btn-ghost" onClick={onClose} aria-label="Close">
              <X size={16} />
            </button>
          </div>
        </header>
        <div className="project-list-body">
          {projects.length === 0 ? (
            <p className="muted center-text">No saved projects yet. Import PDFs to create one.</p>
          ) : null}
          {projects.map((project) => {
            const timestamp = project.updatedAt ?? project.updated_at ?? project.createdAt ?? project.created_at ?? '';
            return (
              <button
                key={project.id}
                className={`project-row${project.id === currentProjectId ? ' project-row--active' : ''}`}
                onClick={() => {
                  onSelect(project);
                  onClose();
                }}
              >
                <FolderOpen size={18} />
                <div className="project-row-text">
                  <strong>{project.name}</strong>
                  {timestamp ? <small>{new Date(timestamp).toLocaleDateString()}</small> : null}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
