import { useCallback, useRef, useState } from 'react';
import type { DrawingGraph } from '../types';

const MAX_HISTORY = 30;

interface UndoRedoControls {
  pushState: (next: DrawingGraph) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

export function useUndoRedo(graph: DrawingGraph, setGraph: (g: DrawingGraph) => void): UndoRedoControls {
  const past = useRef<DrawingGraph[]>([]);
  const future = useRef<DrawingGraph[]>([]);
  const [, forceRender] = useState(0);

  const pushState = useCallback(
    (next: DrawingGraph) => {
      past.current = [...past.current.slice(-(MAX_HISTORY - 1)), graph];
      future.current = [];
      setGraph(next);
      forceRender((n) => n + 1);
    },
    [graph, setGraph],
  );

  const undo = useCallback(() => {
    if (past.current.length === 0) return;
    const previous = past.current[past.current.length - 1];
    past.current = past.current.slice(0, -1);
    future.current = [...future.current, graph];
    setGraph(previous);
    forceRender((n) => n + 1);
  }, [graph, setGraph]);

  const redo = useCallback(() => {
    if (future.current.length === 0) return;
    const next = future.current[future.current.length - 1];
    future.current = future.current.slice(0, -1);
    past.current = [...past.current, graph];
    setGraph(next);
    forceRender((n) => n + 1);
  }, [graph, setGraph]);

  return {
    pushState,
    undo,
    redo,
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
  };
}
