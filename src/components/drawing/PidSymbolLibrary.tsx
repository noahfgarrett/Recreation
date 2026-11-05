import type { DrawingBounds } from '../../types';

type SymbolOrientation = 'left' | 'right' | 'vertical' | 'horizontal';

interface PidSymbolShapeProps {
  bounds: DrawingBounds;
  stroke: string;
  fill: string;
  strokeWidth: number;
  opacity: number;
  symbolType: string;
  orientation?: SymbolOrientation;
}

export const PID_SYMBOL_TYPES = [
  'air_handler',
  'alarm',
  'analyzer',
  'angle_valve',
  'backflow_preventer',
  'backpressure_valve',
  'bag_filter',
  'balancing_valve',
  'ball_valve',
  'blind_flange',
  'blower',
  'boiler',
  'butterfly_valve',
  'cable_tray',
  'cap',
  'cartridge_filter',
  'centrifugal_fan',
  'centrifugal_pump',
  'centrifugal_separator',
  'check_valve',
  'chemical_tote',
  'chiller',
  'circuit_breaker',
  'closed_tank',
  'coil',
  'column',
  'compressor',
  'concentric_reducer',
  'contactor',
  'control_valve',
  'controller',
  'control_panel',
  'conveyor',
  'cooling_tower',
  'covered_tank',
  'correcting_element',
  'cross',
  'cyclone',
  'damper',
  'diaphragm_valve',
  'computer_monitor',
  'dashpot_piston',
  'disconnect_switch',
  'differential_pressure_transmitter',
  'double_check_valve',
  'drain',
  'drive',
  'drum',
  'duct_transition',
  'dryer',
  'eccentric_reducer',
  'ejector',
  'elbow',
  'electric_actuator',
  'equipment',
  'expansion_bellows',
  'expansion_joint',
  'expansion_loop',
  'fail_closed_valve',
  'fail_open_valve',
  'fan',
  'filter',
  'fit',
  'flame_arrester',
  'flange',
  'flanged_valve',
  'flexible_connector',
  'flexible_hose',
  'float_valve',
  'flow_arrow',
  'flow_controller',
  'flow_element',
  'flow_indicator',
  'flow_meter',
  'flow_switch',
  'flow_transmitter',
  'foot_valve',
  'fuse',
  'gate_valve',
  'gauge',
  'globe_valve',
  'ground',
  'hand_switch',
  'handwheel_actuator',
  'heat_exchanger',
  'hopper',
  'horizontal_vessel',
  'indicator_light',
  'instrument',
  'io_point',
  'junction',
  'knife_gate_valve',
  'level_controller',
  'level_element',
  'level_indicator',
  'level_switch',
  'level_transmitter',
  'limit_switch',
  'lcd_monitor',
  'line_blind',
  'local_instrument',
  'mixer',
  'motor',
  'motor_starter',
  'needle_valve',
  'normally_closed_valve',
  'normally_open_valve',
  'offpage',
  'open_tank',
  'orifice_plate',
  'panel',
  'panel_instrument',
  'panelboard',
  'patch_panel',
  'pid_capillary',
  'pid_data',
  'pid_electric',
  'pid_electric_binary',
  'pid_electromagnetic',
  'pid_heat_trace',
  'pid_heated_cooled',
  'pid_hydraulic',
  'pid_mechanical',
  'pid_pneumatic',
  'pid_pneumatic_binary',
  'pid_signal',
  'pipe_break',
  'pipe_anchor',
  'pinch_valve',
  'piston_valve',
  'plate_heat_exchanger',
  'plug_valve',
  'pneumatic_actuator',
  'position_switch',
  'plc',
  'powered_valve',
  'pressure_controller',
  'pressure_element',
  'pressure_indicator',
  'pressure_regulator',
  'pressure_relief_valve',
  'pressure_sensor',
  'pressure_switch',
  'pressure_transmitter',
  'pump',
  'reactor',
  'reducer',
  'reference_circle',
  'reducing_valve',
  'recorder',
  'relay',
  'relief_valve',
  'relief_angle_valve',
  'rupture_disk',
  'rotary_pump',
  'sample_point',
  'safety_valve',
  'scale',
  'separator',
  'sight_glass',
  'silencer',
  'skid',
  'solenoid_valve',
  'spectacle_blind',
  'spray_nozzle',
  'steam_trap',
  'strainer',
  'tank',
  'tank_mixer',
  'tag_circle',
  'tag_square',
  'tee',
  'temperature_controller',
  'temperature_element',
  'temperature_indicator',
  'temperature_switch',
  'temperature_transmitter',
  'terminal_unit',
  'terminal_block',
  'three_way_valve',
  'tit',
  'transformer',
  'union',
  'ups',
  'valve',
  'vent',
  'vertical_pump',
  'vertical_vessel',
  'vessel',
  'vfd',
  'vacuum_breaker',
  'water_meter',
  'wedge_valve',
  'y_strainer',
  'basket_strainer',
  'duplex_strainer',
  'temporary_strainer',
  'static_mixer',
  'inline_mixer',
  'injection_quill',
  'sample_probe',
  'calibration_column',
  'open_drain',
  'closed_drain',
  'floor_drain',
  'cleanout',
  'hose_bib',
  'quick_connect',
  'pipe_support',
  'guide_support',
  'spring_hanger',
  'vent_silencer',
  'relief_stack',
  'flame_detector',
  'gas_detector',
  'smoke_detector',
  'safety_shower',
  'eyewash',
  'fire_damper',
  'duct_filter',
  'duct_coil',
  'vav_box',
  'junction_box',
  'pull_box',
  'control_station',
  'network_switch',
] as const;

export type PidSymbolType = (typeof PID_SYMBOL_TYPES)[number];

export const PID_SYMBOL_CATEGORIES: Array<{ id: string; label: string; types: PidSymbolType[] }> = [
  {
    id: 'instruments',
    label: 'Instruments',
    types: [
      'instrument',
      'gauge',
      'pressure_indicator',
      'temperature_indicator',
      'level_indicator',
      'flow_meter',
      'flow_transmitter',
      'pressure_transmitter',
      'differential_pressure_transmitter',
      'temperature_transmitter',
      'level_transmitter',
      'pressure_switch',
      'temperature_switch',
      'flow_switch',
      'level_switch',
      'analyzer',
      'controller',
      'recorder',
      'alarm',
      'indicator_light',
      'fit',
      'tit',
      'flow_element',
      'flow_indicator',
      'flow_controller',
      'pressure_element',
      'pressure_controller',
      'temperature_element',
      'temperature_controller',
      'level_element',
      'level_controller',
      'local_instrument',
      'panel_instrument',
    ],
  },
  {
    id: 'valves',
    label: 'Valves',
    types: [
      'valve',
      'gate_valve',
      'globe_valve',
      'ball_valve',
      'butterfly_valve',
      'plug_valve',
      'check_valve',
      'control_valve',
      'relief_valve',
      'pressure_relief_valve',
      'relief_angle_valve',
      'pressure_regulator',
      'knife_gate_valve',
      'pinch_valve',
      'piston_valve',
      'float_valve',
      'safety_valve',
      'vacuum_breaker',
      'foot_valve',
      'flanged_valve',
      'reducing_valve',
      'wedge_valve',
      'needle_valve',
      'diaphragm_valve',
      'solenoid_valve',
      'three_way_valve',
      'angle_valve',
      'normally_open_valve',
      'normally_closed_valve',
      'fail_open_valve',
      'fail_closed_valve',
      'balancing_valve',
      'double_check_valve',
      'backpressure_valve',
      'powered_valve',
    ].filter((type): type is PidSymbolType => symbolNameInTypes(type)),
  },
  {
    id: 'equipment',
    label: 'Equipment',
    types: [
      'pump',
      'centrifugal_pump',
      'vertical_pump',
      'compressor',
      'blower',
      'fan',
      'centrifugal_fan',
      'tank',
      'open_tank',
      'closed_tank',
      'covered_tank',
      'horizontal_vessel',
      'vertical_vessel',
      'vessel',
      'column',
      'reactor',
      'mixer',
      'tank_mixer',
      'inline_mixer',
      'static_mixer',
      'heat_exchanger',
      'plate_heat_exchanger',
      'bag_filter',
      'cartridge_filter',
      'centrifugal_separator',
      'chemical_tote',
      'drum',
      'conveyor',
      'scale',
      'damper',
      'duct_transition',
      'calibration_column',
      'safety_shower',
      'eyewash',
      'duct_filter',
      'duct_coil',
      'vav_box',
      'silencer',
      'ejector',
      'spray_nozzle',
      'hopper',
      'chiller',
      'boiler',
      'cooling_tower',
      'cyclone',
      'air_handler',
      'terminal_unit',
      'coil',
      'filter',
      'separator',
      'dryer',
      'skid',
      'panel',
      'patch_panel',
      'control_panel',
      'computer_monitor',
      'lcd_monitor',
      'motor',
      'drive',
      'dashpot_piston',
      'flame_arrester',
      'rotary_pump',
      'backflow_preventer',
      'water_meter',
      'equipment',
    ],
  },
  {
    id: 'fittings',
    label: 'Fittings / Continuations',
    types: [
      'offpage',
      'flow_arrow',
      'tee',
      'elbow',
      'cross',
      'union',
      'reducer',
      'concentric_reducer',
      'eccentric_reducer',
      'strainer',
      'y_strainer',
      'basket_strainer',
      'duplex_strainer',
      'temporary_strainer',
      'flange',
      'blind_flange',
      'cap',
      'expansion_joint',
      'expansion_loop',
      'flexible_connector',
      'flexible_hose',
      'pipe_break',
      'orifice_plate',
      'spectacle_blind',
      'line_blind',
      'rupture_disk',
      'sight_glass',
      'sample_point',
      'sample_probe',
      'injection_quill',
      'vent',
      'pipe_anchor',
      'pipe_support',
      'guide_support',
      'spring_hanger',
      'open_drain',
      'closed_drain',
      'floor_drain',
      'cleanout',
      'hose_bib',
      'quick_connect',
      'vent_silencer',
      'relief_stack',
      'fire_damper',
      'expansion_bellows',
      'steam_trap',
    ].filter((type): type is PidSymbolType => symbolNameInTypes(type)),
  },
  {
    id: 'signals',
    label: 'Signal / Line Types',
    types: [
      'pid_signal',
      'pid_data',
      'pid_pneumatic',
      'pid_pneumatic_binary',
      'pid_electric',
      'pid_electric_binary',
      'pid_electromagnetic',
      'pid_hydraulic',
      'pid_mechanical',
      'pid_capillary',
      'pid_heat_trace',
      'pid_heated_cooled',
    ],
  },
  {
    id: 'controls',
    label: 'Electrical / Controls',
    types: [
      'junction',
      'drain',
      'io_point',
      'correcting_element',
      'pressure_sensor',
      'reference_circle',
      'tag_circle',
      'tag_square',
      'plc',
      'vfd',
      'transformer',
      'disconnect_switch',
      'circuit_breaker',
      'terminal_block',
      'fuse',
      'relay',
      'contactor',
      'motor_starter',
      'panelboard',
      'ground',
      'cable_tray',
      'ups',
      'junction_box',
      'pull_box',
      'control_station',
      'network_switch',
      'flame_detector',
      'gas_detector',
      'smoke_detector',
      'hand_switch',
      'limit_switch',
      'position_switch',
    ],
  },
  {
    id: 'actuators',
    label: 'Actuators / Accessories',
    types: ['pneumatic_actuator', 'electric_actuator', 'handwheel_actuator'],
  },
];

const symbolTypeSet = new Set<string>(PID_SYMBOL_TYPES);
export const PID_SYMBOL_MASTER_SHEET_PATH = '/pid-symbols/symbol-master.svg';

function symbolNameInTypes(type: string): type is PidSymbolType {
  return (PID_SYMBOL_TYPES as readonly string[]).includes(type);
}

export function PidSymbolShape({
  bounds,
  stroke,
  fill,
  strokeWidth,
  opacity,
  symbolType,
  orientation = 'horizontal',
}: PidSymbolShapeProps) {
  const normalizedType = symbolTypeSet.has(symbolType) ? symbolType : 'equipment';
  const transform = `translate(${bounds.x} ${bounds.y}) scale(${bounds.width / 100} ${bounds.height / 100})`;
  const common = {
    className: 'drawing-canvas__symbol drawing-canvas__pid-symbol',
    'data-symbol-registry': 'recreation-vector-pack',
    'data-symbol-type': normalizedType,
    'data-testid': `pid-symbol-${normalizedType}`,
    fill: 'none',
    opacity,
    stroke,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    strokeWidth,
    transform,
    vectorEffect: 'non-scaling-stroke' as const,
  };
  const fillColor = fill === 'none' || fill === 'transparent' ? '#ffffff' : fill;

  if (normalizedType === 'flow_arrow') {
    const points = orientation === 'left' ? '92 10 8 50 92 90' : '8 10 92 50 8 90';
    return <polygon {...common} points={points} fill={stroke} />;
  }

  if (normalizedType === 'offpage') {
    const points = orientation === 'left' ? '96 12 28 12 4 50 28 88 96 88' : '4 12 72 12 96 50 72 88 4 88';
    return <polygon {...common} points={points} fill={fillColor} />;
  }

  if (
    normalizedType === 'pid_signal' ||
    normalizedType === 'pid_data' ||
    normalizedType === 'pid_pneumatic' ||
    normalizedType === 'pid_pneumatic_binary' ||
    normalizedType === 'pid_electric' ||
    normalizedType === 'pid_electric_binary' ||
    normalizedType === 'pid_electromagnetic' ||
    normalizedType === 'pid_hydraulic' ||
    normalizedType === 'pid_mechanical' ||
    normalizedType === 'pid_capillary' ||
    normalizedType === 'pid_heat_trace' ||
    normalizedType === 'pid_heated_cooled'
  ) {
    const dashByType: Record<string, string | undefined> = {
      pid_capillary: '2 5',
      pid_data: '9 5',
      pid_electric: '3 3',
      pid_electric_binary: '3 3 12 3',
      pid_electromagnetic: '10 4 2 4 2 4',
      pid_hydraulic: '14 4 3 4',
      pid_heated_cooled: '6 3',
      pid_pneumatic: '1 5',
      pid_pneumatic_binary: '1 4 10 4',
      pid_signal: undefined,
    };
    return (
      <g {...common}>
        <line x1="6" y1="50" x2="94" y2="50" strokeDasharray={dashByType[normalizedType]} />
        {normalizedType === 'pid_mechanical' ? <path d="M10 62 L22 38 L34 62 L46 38 L58 62 L70 38 L82 62 L94 38" /> : null}
        {normalizedType === 'pid_heat_trace' || normalizedType === 'pid_heated_cooled' ? <path d="M8 64 C20 36 32 64 44 36 C56 64 68 36 80 64 C86 50 92 50 96 64" /> : null}
        {normalizedType === 'pid_electromagnetic' ? <path d="M18 36 C26 22 38 22 46 36 C54 50 66 50 74 36 M18 64 C26 78 38 78 46 64 C54 50 66 50 74 64" /> : null}
      </g>
    );
  }

  if (normalizedType === 'instrument') {
    return (
      <g {...common}>
        <line x1="50" y1="84" x2="50" y2="100" />
        <circle cx="50" cy="46" r="34" fill={fillColor} />
        <line x1="34" y1="46" x2="66" y2="46" />
        <line x1="50" y1="30" x2="50" y2="62" />
      </g>
    );
  }

  if (normalizedType === 'gauge') {
    return (
      <g {...common}>
        <line x1="50" y1="78" x2="50" y2="96" />
        <circle cx="50" cy="48" r="30" fill={fillColor} />
        <path d="M30 57 A22 22 0 0 1 70 57" />
        <line x1="37" y1="55" x2="41" y2="51" />
        <line x1="63" y1="55" x2="59" y2="51" />
        <line x1="50" y1="50" x2="66" y2="37" />
        <circle cx="50" cy="50" r="2.4" fill={stroke} />
      </g>
    );
  }

  if (normalizedType === 'flow_meter') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="25" y2="52" />
        <line x1="75" y1="52" x2="100" y2="52" />
        <circle cx="50" cy="52" r="25" fill={fillColor} />
        <path d="M36 60 L50 34 L64 60" />
        <line x1="40" y1="68" x2="60" y2="68" />
      </g>
    );
  }

  if (
    normalizedType === 'pressure_indicator' ||
    normalizedType === 'temperature_indicator' ||
    normalizedType === 'level_indicator' ||
    normalizedType === 'flow_transmitter' ||
    normalizedType === 'pressure_transmitter' ||
    normalizedType === 'differential_pressure_transmitter' ||
    normalizedType === 'temperature_transmitter' ||
    normalizedType === 'level_transmitter' ||
    normalizedType === 'pressure_switch' ||
    normalizedType === 'temperature_switch' ||
    normalizedType === 'flow_switch' ||
    normalizedType === 'level_switch' ||
    normalizedType === 'analyzer' ||
    normalizedType === 'controller' ||
    normalizedType === 'recorder' ||
    normalizedType === 'alarm' ||
    normalizedType === 'indicator_light' ||
    normalizedType === 'fit' ||
    normalizedType === 'tit' ||
    normalizedType === 'flow_element' ||
    normalizedType === 'flow_indicator' ||
    normalizedType === 'flow_controller' ||
    normalizedType === 'pressure_element' ||
    normalizedType === 'pressure_controller' ||
    normalizedType === 'temperature_element' ||
    normalizedType === 'temperature_controller' ||
    normalizedType === 'level_element' ||
    normalizedType === 'level_controller' ||
    normalizedType === 'local_instrument' ||
    normalizedType === 'panel_instrument'
  ) {
    const codeByType: Record<string, string> = {
      analyzer: 'A',
      controller: 'C',
      differential_pressure_transmitter: 'DPT',
      fit: 'FIT',
      alarm: 'A',
      flow_controller: 'FIC',
      flow_element: 'FE',
      flow_indicator: 'FI',
      flow_switch: 'FS',
      flow_transmitter: 'FT',
      indicator_light: 'L',
      level_controller: 'LIC',
      level_element: 'LE',
      level_indicator: 'LI',
      level_switch: 'LS',
      level_transmitter: 'LT',
      local_instrument: 'L',
      panel_instrument: 'P',
      pressure_controller: 'PIC',
      pressure_element: 'PE',
      pressure_indicator: 'PI',
      pressure_switch: 'PS',
      pressure_transmitter: 'PT',
      recorder: 'R',
      temperature_controller: 'TIC',
      temperature_element: 'TE',
      temperature_indicator: 'TI',
      temperature_switch: 'TS',
      temperature_transmitter: 'TT',
      tit: 'TIT',
    };
    const code = codeByType[normalizedType] ?? 'I';
    return (
      <g {...common}>
        <line x1="50" y1="84" x2="50" y2="100" />
        <circle cx="50" cy="44" r="32" fill={fillColor} />
        {normalizedType.endsWith('_transmitter') || normalizedType.endsWith('_controller') || normalizedType === 'controller' || normalizedType === 'panel_instrument' ? (
          <line x1="18" y1="44" x2="82" y2="44" />
        ) : null}
        {normalizedType.endsWith('_switch') ? <path d="M30 66 L70 66 M50 66 L66 28" /> : null}
        {normalizedType === 'local_instrument' ? <path d="M22 68 L78 68" /> : null}
        {normalizedType === 'analyzer' ? <path d="M32 60 L50 24 L68 60 Z" /> : null}
        {normalizedType === 'differential_pressure_transmitter' ? <path d="M18 72 H82 M30 72 V84 M70 72 V84" /> : null}
        {normalizedType === 'recorder' ? <path d="M30 62 L42 52 L54 58 L68 34" /> : null}
        {normalizedType === 'alarm' ? <path d="M30 66 C34 50 66 50 70 66 M26 70 H74" /> : null}
        {normalizedType === 'indicator_light' ? <path d="M50 12 V0 M50 88 V100 M12 44 H0 M88 44 H100 M24 18 L12 6 M76 18 L88 6" /> : null}
        <text
          x="50"
          y="50"
          fill={stroke}
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize={code.length > 1 ? 20 : 24}
          fontWeight={700}
          stroke="none"
          textAnchor="middle"
        >
          {code}
        </text>
      </g>
    );
  }

  if (normalizedType === 'valve') {
    if (orientation === 'vertical') {
      return (
        <g {...common}>
          <line x1="50" y1="0" x2="50" y2="100" />
          <polygon points="20 18 80 18 50 50" fill={fillColor} />
          <polygon points="20 82 80 82 50 50" fill={fillColor} />
          <line x1="20" y1="18" x2="80" y2="18" />
        </g>
      );
    }
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="100" y2="50" />
        <polygon points="16 18 16 82 50 50" fill={fillColor} />
        <polygon points="84 18 84 82 50 50" fill={fillColor} />
        <line x1="84" y1="18" x2="84" y2="82" />
      </g>
    );
  }

  if (normalizedType === 'gate_valve') {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="100" y2="50" />
        <polygon points="16 18 16 82 50 50" fill={fillColor} />
        <polygon points="84 18 84 82 50 50" fill={fillColor} />
        <line x1="50" y1="50" x2="50" y2="16" />
        <line x1="34" y1="16" x2="66" y2="16" />
      </g>
    );
  }

  if (normalizedType === 'check_valve') {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="100" y2="50" />
        <polygon points="18 22 18 78 54 50" fill={fillColor} />
        <line x1="68" y1="24" x2="68" y2="76" />
        <path d="M58 32 C70 38 70 62 58 68" />
      </g>
    );
  }

  if (normalizedType === 'control_valve') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="100" y2="52" />
        <polygon points="18 24 18 80 50 52" fill={fillColor} />
        <polygon points="82 24 82 80 50 52" fill={fillColor} />
        <line x1="50" y1="52" x2="50" y2="20" />
        <circle cx="50" cy="14" r="10" fill={fillColor} />
      </g>
    );
  }

  if (normalizedType === 'relief_valve') {
    return (
      <g {...common}>
        <line x1="0" y1="58" x2="100" y2="58" />
        <polygon points="20 30 20 86 54 58" fill={fillColor} />
        <line x1="66" y1="58" x2="66" y2="20" />
        <path d="M54 24 C62 8 78 8 86 24" />
        <line x1="70" y1="20" x2="70" y2="34" />
      </g>
    );
  }

  if (
    normalizedType === 'globe_valve' ||
    normalizedType === 'ball_valve' ||
    normalizedType === 'butterfly_valve' ||
    normalizedType === 'plug_valve' ||
    normalizedType === 'needle_valve' ||
    normalizedType === 'diaphragm_valve' ||
    normalizedType === 'solenoid_valve' ||
    normalizedType === 'three_way_valve' ||
    normalizedType === 'angle_valve' ||
    normalizedType === 'flanged_valve' ||
    normalizedType === 'reducing_valve' ||
    normalizedType === 'wedge_valve' ||
    normalizedType === 'normally_open_valve' ||
    normalizedType === 'normally_closed_valve' ||
    normalizedType === 'fail_open_valve' ||
    normalizedType === 'fail_closed_valve' ||
    normalizedType === 'balancing_valve' ||
    normalizedType === 'double_check_valve' ||
    normalizedType === 'backpressure_valve' ||
    normalizedType === 'powered_valve' ||
    normalizedType === 'pressure_relief_valve' ||
    normalizedType === 'relief_angle_valve' ||
    normalizedType === 'pressure_regulator' ||
    normalizedType === 'knife_gate_valve' ||
    normalizedType === 'pinch_valve' ||
    normalizedType === 'piston_valve' ||
    normalizedType === 'float_valve' ||
    normalizedType === 'safety_valve' ||
    normalizedType === 'vacuum_breaker' ||
    normalizedType === 'foot_valve'
  ) {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="100" y2="50" />
        {normalizedType === 'angle_valve' || normalizedType === 'relief_angle_valve' ? <line x1="50" y1="50" x2="50" y2="100" /> : null}
        {normalizedType === 'three_way_valve' ? <line x1="50" y1="50" x2="50" y2="0" /> : null}
        {normalizedType === 'flanged_valve' ? (
          <>
            <line x1="14" y1="18" x2="14" y2="82" />
            <line x1="86" y1="18" x2="86" y2="82" />
          </>
        ) : null}
        <polygon points="16 18 16 82 50 50" fill={fillColor} />
        <polygon points="84 18 84 82 50 50" fill={fillColor} />
        {normalizedType === 'globe_valve' ? <circle cx="50" cy="50" r="17" fill={fillColor} /> : null}
        {normalizedType === 'ball_valve' ? <circle cx="50" cy="50" r="13" fill={fillColor} /> : null}
        {normalizedType === 'butterfly_valve' ? <line x1="30" y1="28" x2="70" y2="72" /> : null}
        {normalizedType === 'plug_valve' ? <rect x="38" y="38" width="24" height="24" fill={fillColor} /> : null}
        {normalizedType === 'needle_valve' ? <path d="M50 50 L50 16 M38 16 L62 16 M50 50 L68 26" /> : null}
        {normalizedType === 'diaphragm_valve' ? <path d="M26 30 Q50 8 74 30" /> : null}
        {normalizedType === 'solenoid_valve' ? <rect x="37" y="6" width="26" height="18" fill={fillColor} /> : null}
        {normalizedType === 'reducing_valve' ? <path d="M22 88 L78 12" /> : null}
        {normalizedType === 'wedge_valve' ? <path d="M34 20 L66 80 M66 20 L34 80" /> : null}
        {normalizedType === 'normally_open_valve' ? <path d="M40 12 L60 12" /> : null}
        {normalizedType === 'normally_closed_valve' ? <path d="M40 12 L60 32" /> : null}
        {normalizedType === 'fail_open_valve' ? <path d="M30 12 L70 12 M50 12 L50 28" /> : null}
        {normalizedType === 'fail_closed_valve' ? <path d="M30 12 L70 32 M50 22 L50 36" /> : null}
        {normalizedType === 'balancing_valve' ? <path d="M34 66 L66 34 M36 34 L64 66" /> : null}
        {normalizedType === 'double_check_valve' ? <path d="M25 28 L44 50 L25 72 M56 28 L75 50 L56 72" /> : null}
        {normalizedType === 'backpressure_valve' ? <path d="M30 24 C44 10 66 10 80 24 M70 18 L80 24 L74 34" /> : null}
        {normalizedType === 'pinch_valve' ? <path d="M28 26 C42 42 42 58 28 74 M72 26 C58 42 58 58 72 74" /> : null}
        {normalizedType === 'piston_valve' ? (
          <>
            <line x1="50" y1="50" x2="50" y2="14" />
            <rect x="34" y="8" width="32" height="16" fill={fillColor} />
          </>
        ) : null}
        {normalizedType === 'float_valve' ? (
          <>
            <line x1="50" y1="50" x2="68" y2="18" />
            <circle cx="78" cy="12" r="10" fill={fillColor} />
          </>
        ) : null}
        {normalizedType === 'safety_valve' ? (
          <>
            <line x1="66" y1="50" x2="66" y2="18" />
            <path d="M52 20 C58 6 78 6 84 20 M60 26 H78 M60 32 H78" />
          </>
        ) : null}
        {normalizedType === 'vacuum_breaker' ? <path d="M38 18 C38 6 62 6 62 18 V36 M30 36 H70" /> : null}
        {normalizedType === 'foot_valve' ? (
          <>
            <path d="M62 24 L76 50 L62 76" />
            <path d="M26 86 H74 M32 92 H68" />
          </>
        ) : null}
        {normalizedType === 'knife_gate_valve' ? <path d="M50 50 L50 12 M36 12 H64 M38 20 L62 80" /> : null}
        {normalizedType === 'pressure_regulator' ? (
          <>
            <line x1="50" y1="50" x2="50" y2="18" />
            <path d="M34 22 H66 M38 28 H62 M42 34 H58" />
            <path d="M58 18 C72 12 82 22 78 36" />
          </>
        ) : null}
        {normalizedType === 'powered_valve' ? (
          <>
            <line x1="50" y1="50" x2="50" y2="20" />
            <rect x="34" y="6" width="32" height="18" rx="3" fill={fillColor} />
          </>
        ) : null}
        {normalizedType === 'pressure_relief_valve' || normalizedType === 'relief_angle_valve' ? (
          <>
            <line x1="66" y1="50" x2="66" y2="18" />
            <path d="M50 22 C58 4 78 4 86 22" />
            <line x1="72" y1="18" x2="72" y2="34" />
          </>
        ) : null}
      </g>
    );
  }

  if (normalizedType === 'pneumatic_actuator' || normalizedType === 'electric_actuator' || normalizedType === 'handwheel_actuator') {
    return (
      <g {...common}>
        <line x1="50" y1="54" x2="50" y2="100" />
        {normalizedType === 'pneumatic_actuator' ? <path d="M22 24 C22 8 78 8 78 24 L70 54 L30 54 Z" fill={fillColor} /> : null}
        {normalizedType === 'electric_actuator' ? <rect x="24" y="14" width="52" height="40" rx="4" fill={fillColor} /> : null}
        {normalizedType === 'handwheel_actuator' ? (
          <>
            <circle cx="50" cy="34" r="24" fill={fillColor} />
            <line x1="26" y1="34" x2="74" y2="34" />
            <line x1="50" y1="10" x2="50" y2="58" />
          </>
        ) : null}
      </g>
    );
  }

  if (normalizedType === 'pump' || normalizedType === 'centrifugal_pump') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="22" y2="52" />
        <line x1="78" y1="52" x2="100" y2="52" />
        <circle cx="50" cy="50" r="30" fill={fillColor} />
        <path d="M34 39 C48 22 74 36 72 50 C70 64 48 76 34 61" />
        {normalizedType === 'centrifugal_pump' ? <path d="M72 40 Q88 44 86 58 Q82 73 66 70" /> : null}
        <path d="M28 84 L72 84 L84 96 L16 96 Z" />
      </g>
    );
  }

  if (normalizedType === 'vertical_pump') {
    return (
      <g {...common}>
        <line x1="50" y1="0" x2="50" y2="18" />
        <line x1="50" y1="82" x2="50" y2="100" />
        <circle cx="50" cy="50" r="28" fill={fillColor} />
        <path d="M39 66 C27 48 42 26 58 34 C72 42 66 64 47 68" />
        <path d="M25 82 L75 82" />
      </g>
    );
  }

  if (normalizedType === 'rotary_pump') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        <circle cx="50" cy="50" r="30" fill={fillColor} />
        <circle cx="40" cy="50" r="10" />
        <circle cx="60" cy="50" r="10" />
        <path d="M26 84 L74 84" />
      </g>
    );
  }

  if (normalizedType === 'compressor') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        <circle cx="50" cy="50" r="31" fill={fillColor} />
        <path d="M28 65 L70 50 L28 35 Z" />
        <path d="M26 88 L74 88" />
        <path d="M34 22 C48 12 66 16 76 30" />
      </g>
    );
  }

  if (normalizedType === 'fan' || normalizedType === 'centrifugal_fan') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        {normalizedType === 'centrifugal_fan' ? <path d="M22 30 C42 6 78 18 82 50 C86 82 44 88 24 64 Z" fill={fillColor} /> : <circle cx="50" cy="50" r="31" fill={fillColor} />}
        <path d="M50 50 Q58 32 50 18" />
        <path d="M50 50 Q66 58 78 46" />
        <path d="M50 50 Q34 60 25 76" />
        <circle cx="50" cy="50" r="4" fill={fillColor} />
      </g>
    );
  }

  if (normalizedType === 'blower') {
    return (
      <g {...common}>
        <line x1="0" y1="58" x2="22" y2="58" />
        <line x1="80" y1="42" x2="100" y2="42" />
        <path d="M24 34 C38 12 78 20 82 48 C86 76 46 84 26 62 Z" fill={fillColor} />
        <path d="M38 58 C48 40 64 42 70 50" />
        <path d="M26 88 L78 88" />
      </g>
    );
  }

  if (normalizedType === 'backflow_preventer' || normalizedType === 'water_meter') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="18" y2="52" />
        <line x1="82" y1="52" x2="100" y2="52" />
        {normalizedType === 'water_meter' ? (
          <>
            <circle cx="50" cy="52" r="24" fill={fillColor} />
            <path d="M34 58 A18 18 0 0 1 66 58" />
            <line x1="50" y1="52" x2="64" y2="40" />
          </>
        ) : (
          <>
            <rect x="18" y="30" width="64" height="44" rx="8" fill={fillColor} />
            <path d="M30 52 L44 40 L44 64 Z" />
            <path d="M70 52 L56 40 L56 64 Z" />
          </>
        )}
      </g>
    );
  }

  if (normalizedType === 'tank' || normalizedType === 'open_tank' || normalizedType === 'closed_tank' || normalizedType === 'covered_tank') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="22" y2="52" />
        <line x1="78" y1="52" x2="100" y2="52" />
        {normalizedType === 'open_tank' ? <path d="M26 22 L26 80 C26 90 74 90 74 80 L74 22" fill={fillColor} /> : <path d="M26 20 C26 10 74 10 74 20 L74 80 C74 90 26 90 26 80 Z" fill={fillColor} />}
        {normalizedType === 'covered_tank' ? <path d="M24 22 L50 8 L76 22" /> : null}
        {normalizedType !== 'open_tank' ? <ellipse cx="50" cy="22" rx="24" ry="7" /> : <path d="M26 22 C34 30 66 30 74 22" />}
        <ellipse cx="50" cy="78" rx="24" ry="7" />
        {normalizedType === 'closed_tank' ? <line x1="26" y1="50" x2="74" y2="50" /> : null}
      </g>
    );
  }

  if (normalizedType === 'vessel') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="18" y2="52" />
        <line x1="82" y1="52" x2="100" y2="52" />
        <path d="M22 16 C22 8 78 8 78 16 L78 84 C78 92 22 92 22 84 Z" fill={fillColor} />
        <line x1="50" y1="0" x2="50" y2="16" />
        <line x1="50" y1="84" x2="50" y2="100" />
        <line x1="22" y1="50" x2="78" y2="50" />
      </g>
    );
  }

  if (normalizedType === 'horizontal_vessel' || normalizedType === 'vertical_vessel') {
    if (normalizedType === 'horizontal_vessel') {
      return (
        <g {...common}>
          <line x1="0" y1="52" x2="18" y2="52" />
          <line x1="82" y1="52" x2="100" y2="52" />
          <path d="M22 30 C14 30 14 70 22 70 L78 70 C86 70 86 30 78 30 Z" fill={fillColor} />
          <line x1="32" y1="70" x2="28" y2="86" />
          <line x1="68" y1="70" x2="72" y2="86" />
        </g>
      );
    }
    return (
      <g {...common}>
        <line x1="50" y1="0" x2="50" y2="14" />
        <line x1="50" y1="86" x2="50" y2="100" />
        <path d="M28 16 C28 8 72 8 72 16 L72 84 C72 92 28 92 28 84 Z" fill={fillColor} />
        <ellipse cx="50" cy="18" rx="22" ry="7" />
        <ellipse cx="50" cy="82" rx="22" ry="7" />
      </g>
    );
  }

  if (normalizedType === 'column') {
    return (
      <g {...common}>
        <line x1="50" y1="0" x2="50" y2="12" />
        <line x1="50" y1="88" x2="50" y2="100" />
        <path d="M30 12 C30 5 70 5 70 12 L70 88 C70 95 30 95 30 88 Z" fill={fillColor} />
        <line x1="30" y1="32" x2="70" y2="32" />
        <line x1="30" y1="50" x2="70" y2="50" />
        <line x1="30" y1="68" x2="70" y2="68" />
      </g>
    );
  }

  if (normalizedType === 'inline_mixer' || normalizedType === 'static_mixer') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="18" y2="52" />
        <line x1="82" y1="52" x2="100" y2="52" />
        <rect x="18" y="30" width="64" height="44" rx="6" fill={fillColor} />
        {normalizedType === 'static_mixer' ? (
          <path d="M30 68 L42 36 L54 68 L66 36 M34 36 L46 68 L58 36 L70 68" />
        ) : (
          <>
            <line x1="50" y1="16" x2="50" y2="68" />
            <path d="M34 62 L66 46 M34 46 L66 62" />
          </>
        )}
      </g>
    );
  }

  if (normalizedType === 'reactor' || normalizedType === 'mixer' || normalizedType === 'tank_mixer') {
    return (
      <g {...common}>
        <line x1="50" y1="0" x2="50" y2="16" />
        <path d="M24 18 C24 10 76 10 76 18 L76 78 C76 90 24 90 24 78 Z" fill={fillColor} />
        <line x1="50" y1="16" x2="50" y2="62" />
        <path d="M34 62 L66 46" />
        <path d="M34 46 L66 62" />
        {normalizedType === 'reactor' ? <path d="M24 82 L12 98 M76 82 L88 98" /> : null}
        {normalizedType === 'tank_mixer' ? <path d="M28 38 H72 M34 78 L24 98 M66 78 L76 98" /> : null}
      </g>
    );
  }

  if (normalizedType === 'cyclone') {
    return (
      <g {...common}>
        <line x1="0" y1="35" x2="30" y2="35" />
        <line x1="70" y1="35" x2="100" y2="35" />
        <path d="M24 16 L76 16 L62 58 L52 58 L50 92 L38 58 L24 16 Z" fill={fillColor} />
        <path d="M36 32 C48 22 62 24 70 34" />
      </g>
    );
  }

  if (normalizedType === 'separator') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="22" y2="52" />
        <line x1="78" y1="52" x2="100" y2="52" />
        <path d="M25 18 C25 10 75 10 75 18 L75 82 C75 90 25 90 25 82 Z" fill={fillColor} />
        <line x1="34" y1="40" x2="66" y2="40" />
        <path d="M33 66 C43 54 57 78 68 64" />
      </g>
    );
  }

  if (normalizedType === 'centrifugal_separator') {
    return (
      <g {...common}>
        <line x1="0" y1="34" x2="24" y2="34" />
        <line x1="70" y1="34" x2="100" y2="34" />
        <path d="M24 18 C42 8 72 14 78 38 C84 62 58 76 50 92 L40 92 C48 70 22 62 22 38 C22 30 22 24 24 18 Z" fill={fillColor} />
        <path d="M34 34 C44 22 64 24 70 38 C58 34 46 38 38 48" />
        <line x1="50" y1="76" x2="50" y2="100" />
      </g>
    );
  }

  if (normalizedType === 'filter' || normalizedType === 'bag_filter' || normalizedType === 'cartridge_filter') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        <rect x="22" y="22" width="56" height="56" fill={fillColor} />
        {normalizedType === 'bag_filter' ? <path d="M36 30 C30 48 32 66 42 74 M52 30 C46 48 48 66 58 74 M66 30 C60 48 62 66 72 74" /> : null}
        {normalizedType === 'cartridge_filter' ? <path d="M34 30 V74 M44 30 V74 M56 30 V74 M66 30 V74" /> : null}
        {normalizedType === 'filter' ? (
          <>
            <line x1="32" y1="74" x2="50" y2="26" />
            <line x1="48" y1="74" x2="66" y2="26" />
          </>
        ) : null}
        <line x1="28" y1="52" x2="72" y2="52" />
      </g>
    );
  }

  if (normalizedType === 'strainer' || normalizedType === 'y_strainer' || normalizedType === 'basket_strainer' || normalizedType === 'duplex_strainer' || normalizedType === 'temporary_strainer') {
    return (
      <g {...common}>
        <line x1="0" y1="48" x2="20" y2="48" />
        <line x1="80" y1="48" x2="100" y2="48" />
        <path d="M20 26 L70 26 L84 48 L70 70 L20 70 Z" fill={fillColor} />
        <path d={normalizedType === 'y_strainer' || normalizedType === 'basket_strainer' ? 'M52 66 L72 94' : 'M40 70 L62 92'} />
        <path d="M34 62 L52 32" />
        <path d="M48 66 L66 36" />
        {normalizedType === 'duplex_strainer' ? <path d="M28 22 C30 8 70 8 72 22 M28 74 C30 88 70 88 72 74" /> : null}
        {normalizedType === 'temporary_strainer' ? <path d="M36 28 L72 48 L36 68 Z" /> : null}
      </g>
    );
  }

  if (normalizedType === 'reducer') {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="16" y2="50" />
        <line x1="84" y1="50" x2="100" y2="50" />
        <path d="M16 28 L52 28 L84 40 L84 60 L52 72 L16 72 Z" fill={fillColor} />
        <line x1="52" y1="28" x2="52" y2="72" />
      </g>
    );
  }

  if (normalizedType === 'concentric_reducer' || normalizedType === 'eccentric_reducer') {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="18" y2="50" />
        <line x1="82" y1="50" x2="100" y2="50" />
        {normalizedType === 'concentric_reducer' ? (
          <path d="M18 28 L52 28 L82 40 L82 60 L52 72 L18 72 Z" fill={fillColor} />
        ) : (
          <path d="M18 36 L52 36 L82 50 L52 64 L18 64 Z" fill={fillColor} />
        )}
        <line x1="52" y1="28" x2="52" y2="72" />
      </g>
    );
  }

  if (
    normalizedType === 'tee' ||
    normalizedType === 'elbow' ||
    normalizedType === 'cross' ||
    normalizedType === 'union' ||
    normalizedType === 'pipe_break' ||
    normalizedType === 'flexible_hose' ||
    normalizedType === 'expansion_loop' ||
    normalizedType === 'orifice_plate' ||
    normalizedType === 'spectacle_blind' ||
    normalizedType === 'line_blind' ||
    normalizedType === 'rupture_disk' ||
    normalizedType === 'sight_glass' ||
    normalizedType === 'sample_point' ||
    normalizedType === 'sample_probe' ||
    normalizedType === 'injection_quill' ||
    normalizedType === 'vent' ||
    normalizedType === 'pipe_anchor' ||
    normalizedType === 'pipe_support' ||
    normalizedType === 'guide_support' ||
    normalizedType === 'spring_hanger' ||
    normalizedType === 'open_drain' ||
    normalizedType === 'closed_drain' ||
    normalizedType === 'floor_drain' ||
    normalizedType === 'cleanout' ||
    normalizedType === 'hose_bib' ||
    normalizedType === 'quick_connect' ||
    normalizedType === 'vent_silencer' ||
    normalizedType === 'relief_stack' ||
    normalizedType === 'fire_damper' ||
    normalizedType === 'expansion_bellows'
  ) {
    return (
      <g {...common}>
        {normalizedType === 'tee' ? <path d="M0 50 H100 M50 50 V10" /> : null}
        {normalizedType === 'elbow' ? <path d="M0 70 H42 Q70 70 70 42 V0" /> : null}
        {normalizedType === 'cross' ? <path d="M0 50 H100 M50 0 V100" /> : null}
        {normalizedType === 'union' ? (
          <>
            <line x1="0" y1="50" x2="100" y2="50" />
            <path d="M34 26 L50 50 L34 74 M66 26 L50 50 L66 74" />
          </>
        ) : null}
        {normalizedType === 'pipe_break' ? <path d="M0 50 H38 M44 30 L36 70 M64 30 L56 70 M62 50 H100" /> : null}
        {normalizedType === 'flexible_hose' ? <path d="M0 50 H18 C26 20 34 80 42 50 C50 20 58 80 66 50 C74 20 82 80 90 50 H100" /> : null}
        {normalizedType === 'expansion_loop' ? <path d="M0 70 H25 V28 H75 V70 H100" /> : null}
        {normalizedType === 'orifice_plate' ? (
          <>
            <line x1="0" y1="50" x2="100" y2="50" />
            <line x1="48" y1="16" x2="48" y2="84" />
            <circle cx="48" cy="50" r="8" fill={fillColor} />
          </>
        ) : null}
        {normalizedType === 'spectacle_blind' ? (
          <>
            <line x1="0" y1="50" x2="30" y2="50" />
            <line x1="70" y1="50" x2="100" y2="50" />
            <circle cx="40" cy="50" r="18" fill={fillColor} />
            <circle cx="62" cy="50" r="18" fill={fillColor} />
            <line x1="52" y1="32" x2="52" y2="68" />
          </>
        ) : null}
        {normalizedType === 'line_blind' ? (
          <>
            <line x1="0" y1="50" x2="100" y2="50" />
            <line x1="48" y1="20" x2="48" y2="80" />
            <path d="M58 24 L76 76" />
          </>
        ) : null}
        {normalizedType === 'rupture_disk' ? (
          <>
            <line x1="0" y1="50" x2="36" y2="50" />
            <line x1="64" y1="50" x2="100" y2="50" />
            <path d="M42 24 C58 36 58 64 42 76 M58 24 C42 36 42 64 58 76" />
          </>
        ) : null}
        {normalizedType === 'sight_glass' ? (
          <>
            <line x1="0" y1="50" x2="28" y2="50" />
            <line x1="72" y1="50" x2="100" y2="50" />
            <rect x="30" y="28" width="40" height="44" rx="10" fill={fillColor} />
            <circle cx="50" cy="50" r="12" />
          </>
        ) : null}
        {normalizedType === 'sample_point' ? <path d="M0 56 H44 V24 M34 24 H54 M44 24 L64 8" /> : null}
        {normalizedType === 'sample_probe' ? <path d="M0 56 H36 V24 M30 24 H54 M42 24 L72 10 M50 34 L78 20" /> : null}
        {normalizedType === 'injection_quill' ? <path d="M0 56 H40 V20 M30 20 H58 M48 20 L74 48 M60 48 L82 48" /> : null}
        {normalizedType === 'vent' ? <path d="M0 70 H50 V28 M34 28 H66 M40 18 H60 M46 8 H54" /> : null}
        {normalizedType === 'pipe_anchor' ? <path d="M0 50 H100 M50 50 V80 M30 80 H70 M36 90 H64" /> : null}
        {normalizedType === 'pipe_support' ? <path d="M0 42 H100 M50 42 V74 M32 74 H68 M40 86 H60" /> : null}
        {normalizedType === 'guide_support' ? <path d="M0 42 H100 M34 30 V58 M66 30 V58 M50 42 V78 M28 78 H72" /> : null}
        {normalizedType === 'spring_hanger' ? <path d="M50 0 V18 M38 18 C62 18 38 34 62 34 C38 34 62 50 38 50 C62 50 38 66 62 66 M50 66 V100" /> : null}
        {normalizedType === 'open_drain' || normalizedType === 'closed_drain' || normalizedType === 'floor_drain' ? (
          <>
            <line x1="0" y1="32" x2="100" y2="32" />
            <line x1="50" y1="32" x2="50" y2="72" />
            <polygon points="32 72 68 72 50 94" fill={normalizedType === 'closed_drain' ? stroke : fillColor} />
            {normalizedType === 'floor_drain' ? <circle cx="50" cy="72" r="24" fill="none" /> : null}
          </>
        ) : null}
        {normalizedType === 'cleanout' ? <path d="M0 50 H42 M42 30 H72 V70 H42 V50 M72 36 L86 20" /> : null}
        {normalizedType === 'hose_bib' ? <path d="M0 54 H44 V32 H74 M56 24 H74 M64 32 V60 M52 60 H76" /> : null}
        {normalizedType === 'quick_connect' ? <path d="M0 50 H26 M74 50 H100 M26 30 H52 L74 50 L52 70 H26 Z M44 36 V64" /> : null}
        {normalizedType === 'vent_silencer' ? <path d="M0 64 H40 V24 H72 V64 H100 M48 32 H64 M48 44 H64 M48 56 H64" /> : null}
        {normalizedType === 'relief_stack' ? <path d="M50 100 V22 M34 22 H66 M38 12 H62 M42 2 H58 M58 70 L86 50" /> : null}
        {normalizedType === 'fire_damper' ? (
          <>
            <line x1="0" y1="50" x2="18" y2="50" />
            <line x1="82" y1="50" x2="100" y2="50" />
            <rect x="18" y="28" width="64" height="44" fill={fillColor} />
            <line x1="30" y1="70" x2="70" y2="30" />
            <path d="M42 28 C34 42 50 44 48 58 C62 48 70 58 62 70" />
          </>
        ) : null}
        {normalizedType === 'expansion_bellows' ? (
          <>
            <line x1="0" y1="50" x2="22" y2="50" />
            <line x1="78" y1="50" x2="100" y2="50" />
            <path d="M24 30 L32 70 L40 30 L48 70 L56 30 L64 70 L72 30" />
          </>
        ) : null}
      </g>
    );
  }

  if (normalizedType === 'flange' || normalizedType === 'blind_flange' || normalizedType === 'cap') {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="38" y2="50" />
        {normalizedType !== 'cap' ? <line x1="62" y1="50" x2="100" y2="50" /> : null}
        <line x1="40" y1="20" x2="40" y2="80" />
        <line x1="60" y1="20" x2="60" y2="80" />
        {normalizedType === 'blind_flange' ? <line x1="62" y1="22" x2="80" y2="78" /> : null}
        {normalizedType === 'cap' ? <path d="M40 26 L72 26 L72 74 L40 74" fill={fillColor} /> : null}
      </g>
    );
  }

  if (normalizedType === 'expansion_joint' || normalizedType === 'flexible_connector' || normalizedType === 'steam_trap') {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="20" y2="50" />
        <line x1="80" y1="50" x2="100" y2="50" />
        {normalizedType === 'steam_trap' ? (
          <>
            <path d="M22 28 L78 28 L66 72 L34 72 Z" fill={fillColor} />
            <path d="M38 44 Q50 30 62 44 Q50 58 38 44" />
          </>
        ) : (
          <path d="M22 50 C30 26 38 74 46 50 C54 26 62 74 70 50 C74 38 78 38 80 50" />
        )}
      </g>
    );
  }

  if (
    normalizedType === 'junction' ||
    normalizedType === 'drain' ||
    normalizedType === 'io_point' ||
    normalizedType === 'correcting_element' ||
    normalizedType === 'pressure_sensor' ||
    normalizedType === 'reference_circle' ||
    normalizedType === 'tag_circle' ||
    normalizedType === 'tag_square' ||
    normalizedType === 'plc' ||
    normalizedType === 'vfd' ||
    normalizedType === 'transformer' ||
    normalizedType === 'disconnect_switch' ||
    normalizedType === 'circuit_breaker' ||
    normalizedType === 'terminal_block' ||
    normalizedType === 'fuse' ||
    normalizedType === 'relay' ||
    normalizedType === 'contactor' ||
    normalizedType === 'motor_starter' ||
    normalizedType === 'panelboard' ||
    normalizedType === 'ground' ||
    normalizedType === 'cable_tray' ||
    normalizedType === 'ups' ||
    normalizedType === 'junction_box' ||
    normalizedType === 'pull_box' ||
    normalizedType === 'control_station' ||
    normalizedType === 'network_switch' ||
    normalizedType === 'flame_detector' ||
    normalizedType === 'gas_detector' ||
    normalizedType === 'smoke_detector' ||
    normalizedType === 'hand_switch' ||
    normalizedType === 'limit_switch' ||
    normalizedType === 'position_switch'
  ) {
    return (
      <g {...common}>
        {normalizedType === 'junction' ? (
          <>
            <line x1="0" y1="50" x2="100" y2="50" />
            <line x1="50" y1="0" x2="50" y2="100" />
            <circle cx="50" cy="50" r="7" fill={fillColor} />
          </>
        ) : null}
        {normalizedType === 'drain' ? (
          <>
            <line x1="0" y1="32" x2="100" y2="32" />
            <line x1="50" y1="32" x2="50" y2="72" />
            <polygon points="32 72 68 72 50 94" fill={stroke} />
          </>
        ) : null}
        {normalizedType === 'io_point' ? (
          <>
            <rect x="22" y="22" width="56" height="56" fill={fillColor} />
            <line x1="0" y1="50" x2="22" y2="50" />
            <line x1="78" y1="50" x2="100" y2="50" />
            <circle cx="50" cy="50" r="15" />
          </>
        ) : null}
        {normalizedType === 'correcting_element' ? (
          <>
            <line x1="0" y1="50" x2="30" y2="50" />
            <line x1="70" y1="50" x2="100" y2="50" />
            <path d="M30 25 L70 50 L30 75 Z" fill={fillColor} />
            <line x1="70" y1="25" x2="70" y2="75" />
          </>
        ) : null}
        {normalizedType === 'pressure_sensor' ? (
          <>
            <line x1="50" y1="84" x2="50" y2="100" />
            <circle cx="50" cy="46" r="30" fill={fillColor} />
            <path d="M34 54 A18 18 0 0 1 66 54" />
            <text x="50" y="51" fill={stroke} fontFamily="Arial, Helvetica, sans-serif" fontSize="20" fontWeight={700} stroke="none" textAnchor="middle">
              P
            </text>
          </>
        ) : null}
        {normalizedType === 'reference_circle' || normalizedType === 'tag_circle' ? (
          <>
            <circle cx="50" cy="50" r={normalizedType === 'reference_circle' ? 24 : 18} fill={fillColor} />
            {normalizedType === 'reference_circle' ? <line x1="36" y1="50" x2="64" y2="50" /> : null}
          </>
        ) : null}
        {normalizedType === 'tag_square' ? <rect x="30" y="30" width="40" height="40" fill={fillColor} /> : null}
        {normalizedType === 'plc' || normalizedType === 'vfd' ? (
          <>
            <line x1="0" y1="52" x2="22" y2="52" />
            <line x1="78" y1="52" x2="100" y2="52" />
            <rect x="24" y="18" width="52" height="64" rx="4" fill={fillColor} />
            <path d="M34 30 H66 M34 44 H66 M34 58 H66" />
            {normalizedType === 'vfd' ? <path d="M34 70 L44 62 L54 78 L66 62" /> : <circle cx="64" cy="70" r="5" fill={fillColor} />}
          </>
        ) : null}
        {normalizedType === 'transformer' ? (
          <>
            <line x1="0" y1="52" x2="26" y2="52" />
            <line x1="74" y1="52" x2="100" y2="52" />
            <circle cx="41" cy="52" r="18" fill={fillColor} />
            <circle cx="59" cy="52" r="18" fill={fillColor} />
          </>
        ) : null}
        {normalizedType === 'disconnect_switch' ? <path d="M0 60 H36 M64 60 H100 M36 60 L66 28" /> : null}
        {normalizedType === 'circuit_breaker' ? (
          <>
            <line x1="0" y1="60" x2="30" y2="60" />
            <line x1="70" y1="60" x2="100" y2="60" />
            <rect x="32" y="42" width="36" height="28" rx="4" fill={fillColor} />
            <path d="M42 56 H58 M58 56 L52 48" />
          </>
        ) : null}
        {normalizedType === 'terminal_block' ? (
          <>
            <line x1="0" y1="52" x2="20" y2="52" />
            <line x1="80" y1="52" x2="100" y2="52" />
            <rect x="22" y="28" width="56" height="48" rx="4" fill={fillColor} />
            <path d="M36 28 V76 M50 28 V76 M64 28 V76" />
          </>
        ) : null}
        {normalizedType === 'fuse' ? (
          <>
            <line x1="0" y1="52" x2="30" y2="52" />
            <line x1="70" y1="52" x2="100" y2="52" />
            <rect x="30" y="38" width="40" height="28" rx="4" fill={fillColor} />
            <path d="M40 62 L60 42" />
          </>
        ) : null}
        {normalizedType === 'relay' || normalizedType === 'contactor' ? (
          <>
            <line x1="0" y1="56" x2="28" y2="56" />
            <line x1="72" y1="56" x2="100" y2="56" />
            <rect x="30" y="24" width="40" height="54" rx="4" fill={fillColor} />
            <path d="M38 34 C48 24 52 44 62 34 M38 46 C48 36 52 56 62 46" />
            {normalizedType === 'contactor' ? <path d="M38 66 H62 M44 60 L56 72" /> : <circle cx="58" cy="66" r="5" fill={fillColor} />}
          </>
        ) : null}
        {normalizedType === 'motor_starter' || normalizedType === 'panelboard' || normalizedType === 'ups' ? (
          <>
            <line x1="0" y1="52" x2="22" y2="52" />
            <line x1="78" y1="52" x2="100" y2="52" />
            <rect x="24" y="14" width="52" height="72" rx="4" fill={fillColor} />
            {normalizedType === 'motor_starter' ? (
              <>
                <circle cx="50" cy="38" r="14" fill={fillColor} />
                <path d="M40 48 V32 L50 44 L60 32 V48" />
                <path d="M34 64 H66 M34 74 H66" />
              </>
            ) : null}
            {normalizedType === 'panelboard' ? <path d="M34 26 H66 M34 38 H66 M34 50 H66 M34 62 H66 M34 74 H66" /> : null}
            {normalizedType === 'ups' ? <path d="M36 34 H64 V58 H36 Z M40 70 C48 60 56 80 64 70" /> : null}
          </>
        ) : null}
        {normalizedType === 'ground' ? <path d="M50 8 V48 M28 48 H72 M34 62 H66 M40 76 H60 M46 90 H54" /> : null}
        {normalizedType === 'cable_tray' ? (
          <>
            <path d="M8 30 H92 V70 H8 Z" fill={fillColor} />
            <path d="M20 30 V70 M34 30 V70 M48 30 V70 M62 30 V70 M76 30 V70" />
          </>
        ) : null}
        {normalizedType === 'junction_box' || normalizedType === 'pull_box' || normalizedType === 'control_station' || normalizedType === 'network_switch' ? (
          <>
            <line x1="0" y1="52" x2="22" y2="52" />
            <line x1="78" y1="52" x2="100" y2="52" />
            <rect x="24" y="22" width="52" height="56" rx="4" fill={fillColor} />
            {normalizedType === 'junction_box' ? <path d="M36 34 H64 M36 52 H64 M36 70 H64" /> : null}
            {normalizedType === 'pull_box' ? <path d="M36 36 H64 M36 64 H64 M50 36 V64" /> : null}
            {normalizedType === 'control_station' ? <path d="M36 36 H64 M40 54 H60 M42 68 H58 M64 36 L70 28" /> : null}
            {normalizedType === 'network_switch' ? <path d="M34 40 H66 M34 52 H66 M34 64 H66 M40 76 V88 M50 76 V88 M60 76 V88" /> : null}
          </>
        ) : null}
        {normalizedType === 'flame_detector' || normalizedType === 'gas_detector' || normalizedType === 'smoke_detector' ? (
          <>
            <line x1="50" y1="78" x2="50" y2="100" />
            <circle cx="50" cy="42" r="28" fill={fillColor} />
            {normalizedType === 'flame_detector' ? <path d="M42 60 C36 44 52 44 50 28 C62 40 68 48 60 62" /> : null}
            {normalizedType === 'gas_detector' ? <path d="M36 56 C42 42 58 42 64 56 M40 66 H60" /> : null}
            {normalizedType === 'smoke_detector' ? <path d="M32 56 C42 46 58 66 68 56 M34 42 C44 32 56 52 66 42" /> : null}
            <text x="50" y="48" fill={stroke} fontFamily="Arial, Helvetica, sans-serif" fontSize="14" fontWeight={700} stroke="none" textAnchor="middle">
              {normalizedType === 'flame_detector' ? 'FD' : normalizedType === 'gas_detector' ? 'GD' : 'SD'}
            </text>
          </>
        ) : null}
        {normalizedType === 'hand_switch' || normalizedType === 'limit_switch' || normalizedType === 'position_switch' ? (
          <>
            <line x1="0" y1="60" x2="35" y2="60" />
            <line x1="65" y1="60" x2="100" y2="60" />
            <circle cx="50" cy="60" r="22" fill={fillColor} />
            <text x="50" y="66" fill={stroke} fontFamily="Arial, Helvetica, sans-serif" fontSize="18" fontWeight={700} stroke="none" textAnchor="middle">
              {normalizedType === 'hand_switch' ? 'HS' : normalizedType === 'limit_switch' ? 'LS' : 'ZS'}
            </text>
          </>
        ) : null}
      </g>
    );
  }

  if (normalizedType === 'heat_exchanger') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="18" y2="52" />
        <line x1="82" y1="52" x2="100" y2="52" />
        <rect x="20" y="18" width="60" height="64" rx="10" fill={fillColor} />
        <line x1="30" y1="34" x2="70" y2="34" />
        <line x1="30" y1="50" x2="70" y2="50" />
        <line x1="30" y1="66" x2="70" y2="66" />
        <line x1="38" y1="18" x2="38" y2="82" />
        <line x1="62" y1="18" x2="62" y2="82" />
      </g>
    );
  }

  if (normalizedType === 'plate_heat_exchanger') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="18" y2="52" />
        <line x1="82" y1="52" x2="100" y2="52" />
        <rect x="20" y="18" width="60" height="64" rx="8" fill={fillColor} />
        <path d="M32 24 L46 76 M46 24 L60 76 M60 24 L74 76" />
        <line x1="20" y1="34" x2="80" y2="34" />
        <line x1="20" y1="66" x2="80" y2="66" />
      </g>
    );
  }

  if (normalizedType === 'silencer' || normalizedType === 'ejector' || normalizedType === 'spray_nozzle' || normalizedType === 'hopper' || normalizedType === 'flame_arrester') {
    return (
      <g {...common}>
        {normalizedType === 'silencer' ? (
          <>
            <line x1="0" y1="52" x2="18" y2="52" />
            <line x1="82" y1="52" x2="100" y2="52" />
            <rect x="20" y="28" width="60" height="48" rx="12" fill={fillColor} />
            <path d="M32 36 H68 M32 52 H68 M32 68 H68" />
          </>
        ) : null}
        {normalizedType === 'ejector' ? (
          <>
            <line x1="0" y1="52" x2="20" y2="52" />
            <line x1="80" y1="52" x2="100" y2="52" />
            <path d="M20 36 L56 48 L80 30 L80 74 L56 56 L20 68 Z" fill={fillColor} />
            <line x1="50" y1="0" x2="50" y2="42" />
          </>
        ) : null}
        {normalizedType === 'spray_nozzle' ? (
          <>
            <line x1="50" y1="0" x2="50" y2="34" />
            <path d="M32 34 H68 L56 56 H44 Z" fill={fillColor} />
            <path d="M34 70 L20 94 M50 70 V98 M66 70 L80 94" strokeDasharray="4 4" />
          </>
        ) : null}
        {normalizedType === 'hopper' ? (
          <>
            <line x1="50" y1="0" x2="50" y2="16" />
            <path d="M22 18 H78 L64 70 L56 70 V92 H44 V70 H36 Z" fill={fillColor} />
          </>
        ) : null}
        {normalizedType === 'flame_arrester' ? (
          <>
            <line x1="0" y1="52" x2="18" y2="52" />
            <line x1="82" y1="52" x2="100" y2="52" />
            <rect x="20" y="26" width="60" height="52" rx="8" fill={fillColor} />
            <path d="M34 70 C28 54 44 54 42 38 C54 50 64 58 58 72" />
          </>
        ) : null}
      </g>
    );
  }

  if (normalizedType === 'coil') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="18" y2="52" />
        <line x1="82" y1="52" x2="100" y2="52" />
        <rect x="20" y="20" width="60" height="60" fill={fillColor} />
        <path d="M30 76 L42 24 L54 76 L66 24 L76 76" />
      </g>
    );
  }

  if (normalizedType === 'air_handler') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="15" y2="52" />
        <line x1="85" y1="52" x2="100" y2="52" />
        <rect x="16" y="20" width="68" height="60" fill={fillColor} />
        <circle cx="36" cy="50" r="13" />
        <path d="M27 50 C34 36 47 45 45 58" />
        <path d="M56 24 L72 76" />
        <path d="M66 24 L82 76" />
      </g>
    );
  }

  if (normalizedType === 'terminal_unit') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        <rect x="22" y="28" width="56" height="44" fill={fillColor} />
        <line x1="34" y1="40" x2="66" y2="40" />
        <line x1="34" y1="52" x2="66" y2="52" />
        <line x1="34" y1="64" x2="66" y2="64" />
      </g>
    );
  }

  if (normalizedType === 'drive') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="24" y2="52" />
        <line x1="76" y1="52" x2="100" y2="52" />
        <rect x="25" y="22" width="50" height="56" fill={fillColor} />
        <path d="M32 52 L40 34 L50 70 L60 34 L70 52" />
      </g>
    );
  }

  if (normalizedType === 'motor') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="24" y2="52" />
        <line x1="76" y1="52" x2="100" y2="52" />
        <circle cx="50" cy="50" r="28" fill={fillColor} />
        <path d="M34 64 L34 36 L50 54 L66 36 L66 64" />
        <path d="M30 84 L70 84" />
      </g>
    );
  }

  if (normalizedType === 'panel' || normalizedType === 'patch_panel' || normalizedType === 'control_panel' || normalizedType === 'computer_monitor' || normalizedType === 'lcd_monitor') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="26" y2="52" />
        <line x1="74" y1="52" x2="100" y2="52" />
        {normalizedType === 'computer_monitor' || normalizedType === 'lcd_monitor' ? (
          <>
            <rect x="22" y="18" width="56" height="44" rx="4" fill={fillColor} />
            <path d="M42 62 L38 82 H62 L58 62" />
            <line x1="34" y1="82" x2="66" y2="82" />
          </>
        ) : (
          <rect x="28" y="14" width="44" height="72" fill={fillColor} />
        )}
        {normalizedType === 'patch_panel' ? (
          <>
            <line x1="36" y1="28" x2="64" y2="28" />
            <line x1="36" y1="42" x2="64" y2="42" />
            <line x1="36" y1="56" x2="64" y2="56" />
            <line x1="36" y1="70" x2="64" y2="70" />
          </>
        ) : null}
        {normalizedType === 'control_panel' || normalizedType === 'panel' ? (
          <>
            <line x1="36" y1="34" x2="64" y2="34" />
            <line x1="36" y1="50" x2="64" y2="50" />
            <line x1="36" y1="66" x2="64" y2="66" />
          </>
        ) : null}
        {normalizedType === 'control_panel' ? <circle cx="50" cy="24" r="6" fill={fillColor} /> : null}
        {normalizedType === 'lcd_monitor' ? <line x1="30" y1="54" x2="70" y2="54" /> : null}
      </g>
    );
  }

  if (normalizedType === 'dashpot_piston') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        <rect x="24" y="28" width="52" height="44" rx="8" fill={fillColor} />
        <line x1="50" y1="28" x2="50" y2="72" />
        <path d="M34 42 H50 M50 62 H66" />
      </g>
    );
  }

  if (normalizedType === 'chiller') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="15" y2="52" />
        <line x1="85" y1="52" x2="100" y2="52" />
        <rect x="16" y="18" width="68" height="64" rx="6" fill={fillColor} />
        <line x1="28" y1="38" x2="72" y2="38" />
        <line x1="28" y1="62" x2="72" y2="62" />
        <path d="M32 28 C42 54 58 46 68 74" />
      </g>
    );
  }

  if (normalizedType === 'boiler') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="18" y2="52" />
        <line x1="82" y1="52" x2="100" y2="52" />
        <rect x="20" y="14" width="60" height="72" rx="12" fill={fillColor} />
        <path d="M34 72 C28 50 47 48 46 28 C62 48 76 58 66 74" />
      </g>
    );
  }

  if (normalizedType === 'dryer') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="24" y2="52" />
        <line x1="76" y1="52" x2="100" y2="52" />
        <rect x="26" y="15" width="21" height="70" rx="8" fill={fillColor} />
        <rect x="53" y="15" width="21" height="70" rx="8" fill={fillColor} />
        <line x1="47" y1="52" x2="53" y2="52" />
        <line x1="31" y1="52" x2="42" y2="52" />
        <line x1="58" y1="52" x2="69" y2="52" />
      </g>
    );
  }

  if (normalizedType === 'cooling_tower') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        <path d="M28 14 L72 14 L82 86 L18 86 Z" fill={fillColor} />
        <line x1="30" y1="40" x2="70" y2="40" />
        <line x1="26" y1="66" x2="74" y2="66" />
        <path d="M40 14 C42 4 58 4 60 14" />
      </g>
    );
  }

  if (normalizedType === 'skid') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="16" y2="52" />
        <line x1="84" y1="52" x2="100" y2="52" />
        <rect x="18" y="22" width="64" height="52" fill={fillColor} />
        <line x1="12" y1="88" x2="88" y2="88" />
        <line x1="34" y1="22" x2="34" y2="74" />
        <line x1="62" y1="22" x2="62" y2="74" />
      </g>
    );
  }

  if (normalizedType === 'chemical_tote' || normalizedType === 'drum') {
    return (
      <g {...common}>
        <line x1="0" y1="52" x2="20" y2="52" />
        <line x1="80" y1="52" x2="100" y2="52" />
        {normalizedType === 'chemical_tote' ? (
          <>
            <rect x="22" y="22" width="56" height="56" rx="4" fill={fillColor} />
            <path d="M30 22 V78 M44 22 V78 M56 22 V78 M70 22 V78 M22 36 H78 M22 64 H78" />
            <rect x="36" y="8" width="28" height="14" rx="3" fill={fillColor} />
          </>
        ) : (
          <>
            <path d="M30 20 C30 10 70 10 70 20 L70 80 C70 90 30 90 30 80 Z" fill={fillColor} />
            <ellipse cx="50" cy="21" rx="20" ry="7" />
            <ellipse cx="50" cy="78" rx="20" ry="7" />
            <path d="M30 42 H70 M30 60 H70" />
          </>
        )}
      </g>
    );
  }

  if (normalizedType === 'calibration_column') {
    return (
      <g {...common}>
        <line x1="50" y1="0" x2="50" y2="18" />
        <line x1="50" y1="82" x2="50" y2="100" />
        <rect x="36" y="18" width="28" height="64" rx="10" fill={fillColor} />
        <path d="M64 30 H76 M64 42 H72 M64 54 H76 M64 66 H72" />
        <path d="M36 30 H24 M36 70 H24" />
      </g>
    );
  }

  if (normalizedType === 'safety_shower' || normalizedType === 'eyewash') {
    return (
      <g {...common}>
        {normalizedType === 'safety_shower' ? (
          <>
            <line x1="50" y1="8" x2="50" y2="92" />
            <path d="M30 22 H70 M36 22 C38 8 62 8 64 22" />
            <path d="M30 36 L20 58 M40 36 L32 60 M50 36 V62 M60 36 L68 60 M70 36 L80 58" strokeDasharray="4 5" />
            <path d="M34 92 H66" />
          </>
        ) : (
          <>
            <line x1="0" y1="70" x2="100" y2="70" />
            <path d="M26 70 C30 52 44 52 50 70 C56 52 70 52 74 70" />
            <circle cx="38" cy="48" r="8" fill={fillColor} />
            <circle cx="62" cy="48" r="8" fill={fillColor} />
            <path d="M38 40 V24 M62 40 V24 M28 24 H72" />
          </>
        )}
      </g>
    );
  }

  if (normalizedType === 'conveyor' || normalizedType === 'scale') {
    return (
      <g {...common}>
        {normalizedType === 'conveyor' ? (
          <>
            <line x1="0" y1="56" x2="18" y2="56" />
            <line x1="82" y1="56" x2="100" y2="56" />
            <path d="M18 40 H82 L70 72 H30 Z" fill={fillColor} />
            <circle cx="32" cy="72" r="8" fill={fillColor} />
            <circle cx="68" cy="72" r="8" fill={fillColor} />
            <path d="M28 40 L72 72" />
          </>
        ) : (
          <>
            <rect x="20" y="60" width="60" height="12" fill={fillColor} />
            <path d="M30 60 L42 30 H58 L70 60" />
            <path d="M42 30 Q50 16 58 30" />
            <line x1="50" y1="30" x2="62" y2="22" />
          </>
        )}
      </g>
    );
  }

  if (normalizedType === 'damper' || normalizedType === 'duct_transition' || normalizedType === 'duct_filter' || normalizedType === 'duct_coil' || normalizedType === 'vav_box') {
    return (
      <g {...common}>
        <line x1="0" y1="50" x2="18" y2="50" />
        <line x1="82" y1="50" x2="100" y2="50" />
        {normalizedType === 'damper' ? (
          <>
            <rect x="18" y="28" width="64" height="44" fill={fillColor} />
            <line x1="28" y1="68" x2="72" y2="32" />
            <line x1="50" y1="20" x2="50" y2="80" />
          </>
        ) : normalizedType === 'duct_transition' ? (
          <path d="M18 34 H42 L82 18 V82 L42 66 H18 Z" fill={fillColor} />
        ) : (
          <>
            <rect x="18" y="28" width="64" height="44" fill={fillColor} />
            {normalizedType === 'duct_filter' ? <path d="M30 68 L44 32 M44 68 L58 32 M58 68 L72 32" /> : null}
            {normalizedType === 'duct_coil' ? <path d="M28 66 L38 34 L48 66 L58 34 L68 66 L76 34" /> : null}
            {normalizedType === 'vav_box' ? <path d="M28 50 H72 M50 28 V72 M34 38 L66 62" /> : null}
          </>
        )}
      </g>
    );
  }

  return (
    <g {...common}>
      <line x1="0" y1="52" x2="18" y2="52" />
      <line x1="82" y1="52" x2="100" y2="52" />
      <rect x="18" y="20" width="64" height="60" rx="4" fill={fillColor} />
      <line x1="18" y1="52" x2="82" y2="52" />
    </g>
  );
}
