import { Lock, Pencil, Trash2, Unlock } from 'lucide-react';
import { useEffect, useRef } from 'react';

export interface ContextMenuAction {
  nodeId: string;
  x: number;
  y: number;
}

interface ContextMenuProps {
  action: ContextMenuAction | null;
  isLocked: boolean;
  onEditTag: (nodeId: string) => void;
  onToggleLock: (nodeId: string) => void;
  onDeleteNode: (nodeId: string) => void;
  onClose: () => void;
}

export function ContextMenu({ action, isLocked, onEditTag, onToggleLock, onDeleteNode, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!action) return;
    function handleClick(e: MouseEvent): void {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    function handleEscape(e: KeyboardEvent): void {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('mousedown', handleClick);
    window.addEventListener('keydown', handleEscape);
    return () => {
      window.removeEventListener('mousedown', handleClick);
      window.removeEventListener('keydown', handleEscape);
    };
  }, [action, onClose]);

  if (!action) return null;

  return (
    <div
      ref={menuRef}
      className="context-menu"
      style={{ top: action.y, left: action.x }}
      role="menu"
    >
      <button role="menuitem" onClick={() => { onEditTag(action.nodeId); onClose(); }}>
        <Pencil size={14} />
        Edit Tag
      </button>
      <button role="menuitem" onClick={() => { onToggleLock(action.nodeId); onClose(); }}>
        {isLocked ? <Unlock size={14} /> : <Lock size={14} />}
        {isLocked ? 'Unlock Position' : 'Lock Position'}
      </button>
      <div className="context-menu-divider" />
      <button role="menuitem" className="context-menu-danger" onClick={() => { onDeleteNode(action.nodeId); onClose(); }}>
        <Trash2 size={14} />
        Delete Node
      </button>
    </div>
  );
}
