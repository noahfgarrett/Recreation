import { Keyboard, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

const SHORTCUTS: Array<{ keys: string; description: string }> = [
  { keys: 'Ctrl + Z', description: 'Undo' },
  { keys: 'Ctrl + Y', description: 'Redo' },
  { keys: 'Ctrl + F', description: 'Focus search bar' },
  { keys: 'Delete', description: 'Delete selected node' },
  { keys: 'Shift + Drag', description: 'Multi-select nodes' },
  { keys: 'Right-click', description: 'Node context menu' },
  { keys: 'Scroll', description: 'Zoom in / out' },
  { keys: '?', description: 'Toggle this reference' },
];

export function ShortcutsModal() {
  const [isOpen, setIsOpen] = useState(false);

  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === '?' && !e.metaKey && !e.ctrlKey && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        toggle();
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, toggle]);

  return (
    <>
      <button className="shortcuts-trigger" onClick={toggle} title="Keyboard shortcuts (?)">
        <Keyboard size={16} />
      </button>
      {isOpen ? (
        <div className="shortcuts-overlay" onClick={() => setIsOpen(false)}>
          <div className="shortcuts-modal" onClick={(e) => e.stopPropagation()}>
            <header>
              <h2>Keyboard Shortcuts</h2>
              <button onClick={() => setIsOpen(false)} aria-label="Close">
                <X size={16} />
              </button>
            </header>
            <dl className="shortcuts-list">
              {SHORTCUTS.map((shortcut) => (
                <div key={shortcut.keys} className="shortcut-row">
                  <dt>
                    {shortcut.keys.split(' + ').map((key, index) => (
                      <span key={key}>
                        {index > 0 ? ' + ' : null}
                        <kbd>{key}</kbd>
                      </span>
                    ))}
                  </dt>
                  <dd>{shortcut.description}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      ) : null}
    </>
  );
}
