import type { NodeKind } from '../types';

interface SymbolProps {
  size?: number;
  className?: string;
}

function Pump({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Pump">
      <circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="2" />
      <polygon points="13,9 13,23 24,16" fill="currentColor" opacity="0.6" />
    </svg>
  );
}

function Vessel({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Vessel">
      <path
        d="M8 11 C8 7, 24 7, 24 11 L24 23 C24 27, 8 27, 8 23 Z"
        stroke="currentColor"
        strokeWidth="2"
        fill="currentColor"
        fillOpacity="0.08"
      />
      <ellipse cx="16" cy="11" rx="8" ry="4" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  );
}

function HeatExchanger({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Heat exchanger">
      <circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="2" />
      <line x1="7" y1="20" x2="25" y2="12" stroke="currentColor" strokeWidth="1.5" />
      <line x1="7" y1="12" x2="25" y2="20" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function ValveSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Valve">
      <polygon
        points="4,7 16,16 4,25"
        stroke="currentColor"
        strokeWidth="2"
        fill="currentColor"
        fillOpacity="0.1"
        strokeLinejoin="round"
      />
      <polygon
        points="28,7 16,16 28,25"
        stroke="currentColor"
        strokeWidth="2"
        fill="currentColor"
        fillOpacity="0.1"
        strokeLinejoin="round"
      />
      <line x1="16" y1="16" x2="16" y2="4" stroke="currentColor" strokeWidth="2" />
      <line x1="11" y1="4" x2="21" y2="4" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function InstrumentBubble({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Instrument">
      <circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="2" />
      <line x1="5" y1="16" x2="27" y2="16" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function JunctionBoxSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Junction box">
      <rect x="5" y="5" width="22" height="22" rx="1" stroke="currentColor" strokeWidth="2" />
      <rect x="3" y="10" width="4" height="4" rx="1" fill="currentColor" opacity="0.5" />
      <rect x="3" y="18" width="4" height="4" rx="1" fill="currentColor" opacity="0.5" />
      <rect x="25" y="10" width="4" height="4" rx="1" fill="currentColor" opacity="0.5" />
      <rect x="25" y="18" width="4" height="4" rx="1" fill="currentColor" opacity="0.5" />
    </svg>
  );
}

function PanelSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Panel">
      <rect x="4" y="5" width="24" height="22" rx="1" stroke="currentColor" strokeWidth="2" />
      <line x1="4" y1="11" x2="28" y2="11" stroke="currentColor" strokeWidth="1.5" opacity="0.5" />
      <line x1="13" y1="11" x2="13" y2="27" stroke="currentColor" strokeWidth="1" opacity="0.3" />
      <line x1="21" y1="11" x2="21" y2="27" stroke="currentColor" strokeWidth="1" opacity="0.3" />
    </svg>
  );
}

function OffPageConnectorSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Off-page connector">
      <polygon
        points="4,6 22,6 28,16 22,26 4,26"
        stroke="currentColor"
        strokeWidth="2"
        fill="currentColor"
        fillOpacity="0.08"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CableEndpointSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Cable endpoint">
      <circle cx="16" cy="16" r="7" stroke="currentColor" strokeWidth="2" />
      <circle cx="16" cy="16" r="2.5" fill="currentColor" />
      <line x1="3" y1="16" x2="9" y2="16" stroke="currentColor" strokeWidth="2" />
      <line x1="23" y1="16" x2="29" y2="16" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function MotorSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Motor">
      <circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="2" />
      <text x="16" y="21" textAnchor="middle" fontSize="14" fill="currentColor" fontWeight="bold">M</text>
    </svg>
  );
}

function BreakerSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Breaker">
      <line x1="16" y1="4" x2="16" y2="12" stroke="currentColor" strokeWidth="2" />
      <line x1="16" y1="12" x2="22" y2="20" stroke="currentColor" strokeWidth="2.5" />
      <line x1="16" y1="20" x2="16" y2="28" stroke="currentColor" strokeWidth="2" />
      <rect x="10" y="18" width="12" height="4" rx="1" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function TransformerSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Transformer">
      <circle cx="12" cy="16" r="7" stroke="currentColor" strokeWidth="2" fill="none" />
      <circle cx="20" cy="16" r="7" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  );
}

function VfdSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="VFD">
      <rect x="5" y="6" width="22" height="20" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M10 20 L14 12 L18 20 L22 12" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />
    </svg>
  );
}

function MccSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="MCC">
      <rect x="4" y="4" width="24" height="24" rx="1" stroke="currentColor" strokeWidth="2" />
      <line x1="4" y1="12" x2="28" y2="12" stroke="currentColor" strokeWidth="1.5" />
      <line x1="4" y1="20" x2="28" y2="20" stroke="currentColor" strokeWidth="1.5" />
      <line x1="16" y1="4" x2="16" y2="28" stroke="currentColor" strokeWidth="1" opacity="0.4" />
    </svg>
  );
}

function SwitchgearSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Switchgear">
      <rect x="4" y="6" width="24" height="20" rx="1" stroke="currentColor" strokeWidth="2" />
      <line x1="4" y1="13" x2="28" y2="13" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="10" cy="9.5" r="2" fill="currentColor" fillOpacity="0.4" />
      <circle cx="16" cy="9.5" r="2" fill="currentColor" fillOpacity="0.4" />
      <circle cx="22" cy="9.5" r="2" fill="currentColor" fillOpacity="0.4" />
      <line x1="10" y1="17" x2="10" y2="22" stroke="currentColor" strokeWidth="1.5" />
      <line x1="16" y1="17" x2="16" y2="22" stroke="currentColor" strokeWidth="1.5" />
      <line x1="22" y1="17" x2="22" y2="22" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function UnknownSymbol({ size = 32, className }: SymbolProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-label="Unknown">
      <rect x="5" y="5" width="22" height="22" rx="3" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3" />
      <text x="16" y="21" textAnchor="middle" fontSize="14" fill="currentColor" fontWeight="bold">
        ?
      </text>
    </svg>
  );
}

const symbolByKind: Record<NodeKind, React.FC<SymbolProps>> = {
  equipment: Pump,
  instrument: InstrumentBubble,
  valve: ValveSymbol,
  panel: PanelSymbol,
  junction_box: JunctionBoxSymbol,
  off_page_connector: OffPageConnectorSymbol,
  cable_endpoint: CableEndpointSymbol,
  motor: MotorSymbol,
  breaker: BreakerSymbol,
  transformer: TransformerSymbol,
  vfd: VfdSymbol,
  mcc: MccSymbol,
  switchgear: SwitchgearSymbol,
  unknown: UnknownSymbol,
};

const symbolById: Record<string, React.FC<SymbolProps>> = {
  pump: Pump,
  vessel: Vessel,
  'heat-exchanger': HeatExchanger,
  valve: ValveSymbol,
  'instrument-bubble': InstrumentBubble,
  'junction-box': JunctionBoxSymbol,
  panel: PanelSymbol,
  'off-page-connector': OffPageConnectorSymbol,
  motor: MotorSymbol,
  breaker: BreakerSymbol,
  transformer: TransformerSymbol,
  vfd: VfdSymbol,
  mcc: MccSymbol,
  switchgear: SwitchgearSymbol,
};

export function PidSymbol({
  kind,
  symbolId,
  size = 32,
  className,
}: SymbolProps & { kind: NodeKind; symbolId: string | null }) {
  const Component = (symbolId ? symbolById[symbolId] : undefined) ?? symbolByKind[kind] ?? UnknownSymbol;
  return <Component size={size} className={className} />;
}
