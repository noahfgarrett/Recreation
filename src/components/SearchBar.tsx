import { ChevronDown, Filter, Search, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConfidenceLevel } from '../lib/graphAdapters';
import type { NodeKind } from '../types';

interface SearchInputProps {
  onSearch: (query: string) => void;
}

interface FilterBarProps {
  onFilterKind: (kind: NodeKind | null) => void;
  activeKind: NodeKind | null;
  onFilterConfidence: (level: ConfidenceLevel | null) => void;
  activeConfidence: ConfidenceLevel | null;
  availableSheets?: number[];
  activeSheet?: number | null;
  onFilterSheet?: (sheet: number | null) => void;
}

interface FilterGroup {
  label: string;
  items: { value: string; label: string }[];
}

const KIND_GROUPS: FilterGroup[] = [
  {
    label: 'Process',
    items: [
      { value: 'equipment', label: 'Equipment' },
      { value: 'instrument', label: 'Instruments' },
      { value: 'valve', label: 'Valves' },
    ],
  },
  {
    label: 'Electrical',
    items: [
      { value: 'motor', label: 'Motors' },
      { value: 'breaker', label: 'Breakers' },
      { value: 'transformer', label: 'Transformers' },
      { value: 'vfd', label: 'VFDs' },
      { value: 'mcc', label: 'MCCs' },
      { value: 'switchgear', label: 'Switchgear' },
    ],
  },
  {
    label: 'Infrastructure',
    items: [
      { value: 'panel', label: 'Panels' },
      { value: 'junction_box', label: 'Junction Boxes' },
      { value: 'off_page_connector', label: 'Off-Page Connectors' },
      { value: 'cable_endpoint', label: 'Cable Endpoints' },
    ],
  },
];

const CONFIDENCE_ITEMS: { value: ConfidenceLevel; label: string; dotClass: string }[] = [
  { value: 'high', label: 'High', dotClass: 'filter-dot--high' },
  { value: 'medium', label: 'Medium', dotClass: 'filter-dot--medium' },
  { value: 'low', label: 'Low', dotClass: 'filter-dot--low' },
];

export function SearchInput({ onSearch }: SearchInputProps): React.ReactElement {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setQuery(e.target.value);
      onSearch(e.target.value);
    },
    [onSearch],
  );

  const clear = useCallback(() => {
    setQuery('');
    onSearch('');
    inputRef.current?.focus();
  }, [onSearch]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="search-input-wrap">
      <Search size={14} className="search-icon" />
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={handleChange}
        placeholder="Search tags... (Ctrl+F)"
        className="search-input"
        aria-label="Search tags"
      />
      {query && (
        <button className="search-clear" onClick={clear} aria-label="Clear search">
          <X size={13} />
        </button>
      )}
    </div>
  );
}

export function FilterBar({ onFilterKind, activeKind, onFilterConfidence, activeConfidence, availableSheets, activeSheet, onFilterSheet }: FilterBarProps): React.ReactElement {
  const clearAll = useCallback(() => {
    onFilterKind(null);
    onFilterConfidence(null);
    onFilterSheet?.(null);
  }, [onFilterKind, onFilterConfidence, onFilterSheet]);

  const hasActiveFilter = activeKind !== null || activeConfidence !== null || activeSheet !== null;

  const kindLabel = activeKind
    ? KIND_GROUPS.flatMap((g) => g.items).find((i) => i.value === activeKind)?.label ?? 'Type'
    : 'Type';

  const confLabel = activeConfidence
    ? CONFIDENCE_ITEMS.find((i) => i.value === activeConfidence)?.label ?? 'Confidence'
    : 'Confidence';

  const sheetLabel = activeSheet !== null ? `Sheet ${activeSheet}` : 'Sheet';

  return (
    <div className="filter-dropdowns">
      <Filter size={13} className="filter-icon" />

      <FilterDropdown
        label={kindLabel}
        isActive={activeKind !== null}
        groups={KIND_GROUPS}
        activeValue={activeKind}
        onSelect={(value) => onFilterKind(value === activeKind ? null : (value as NodeKind))}
        onClear={() => onFilterKind(null)}
      />

      <FilterDropdown
        label={confLabel}
        isActive={activeConfidence !== null}
        items={CONFIDENCE_ITEMS.map((c) => ({ value: c.value, label: c.label, dotClass: c.dotClass }))}
        activeValue={activeConfidence}
        onSelect={(value) => onFilterConfidence(value === activeConfidence ? null : (value as ConfidenceLevel))}
        onClear={() => onFilterConfidence(null)}
      />

      {availableSheets && availableSheets.length > 1 ? (
        <FilterDropdown
          label={sheetLabel}
          isActive={activeSheet !== null}
          items={availableSheets.map((s) => ({ value: String(s), label: `Sheet ${s}` }))}
          activeValue={activeSheet !== null ? String(activeSheet) : null}
          onSelect={(value) => {
            const num = Number(value);
            onFilterSheet?.(num === activeSheet ? null : num);
          }}
          onClear={() => onFilterSheet?.(null)}
        />
      ) : null}

      {hasActiveFilter ? (
        <button className="filter-clear-all" onClick={clearAll} title="Clear all filters">
          <X size={12} />
          Clear
        </button>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */

interface DropdownItem {
  value: string;
  label: string;
  dotClass?: string;
}

interface FilterDropdownProps {
  label: string;
  isActive: boolean;
  items?: DropdownItem[];
  groups?: FilterGroup[];
  activeValue: string | null;
  onSelect: (value: string) => void;
  onClear: () => void;
}

function FilterDropdown({ label, isActive, items, groups, activeValue, onSelect, onClear }: FilterDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    function handleEscape(e: KeyboardEvent): void {
      if (e.key === 'Escape') setIsOpen(false);
    }
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  const renderItems = (list: DropdownItem[]): React.ReactNode =>
    list.map((item) => (
      <button
        key={item.value}
        className={`filter-dropdown-item${activeValue === item.value ? ' filter-dropdown-item--active' : ''}`}
        onClick={() => {
          onSelect(item.value);
          setIsOpen(false);
        }}
      >
        {item.dotClass ? <span className={`filter-dot ${item.dotClass}`} /> : null}
        {item.label}
      </button>
    ));

  return (
    <div className="filter-dropdown" ref={containerRef}>
      <button
        className={`filter-dropdown-trigger${isActive ? ' filter-dropdown-trigger--active' : ''}${isOpen ? ' filter-dropdown-trigger--open' : ''}`}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
      >
        {label}
        <ChevronDown size={12} className={`filter-chevron${isOpen ? ' filter-chevron--open' : ''}`} />
      </button>

      {isOpen ? (
        <div className="filter-dropdown-menu">
          {isActive ? (
            <button
              className="filter-dropdown-item filter-dropdown-item--clear"
              onClick={() => {
                onClear();
                setIsOpen(false);
              }}
            >
              <X size={11} />
              Clear filter
            </button>
          ) : null}

          {groups
            ? groups.map((group) => (
                <div key={group.label} className="filter-dropdown-group">
                  <div className="filter-dropdown-group-label">{group.label}</div>
                  {renderItems(group.items)}
                </div>
              ))
            : null}

          {items ? renderItems(items) : null}
        </div>
      ) : null}
    </div>
  );
}
