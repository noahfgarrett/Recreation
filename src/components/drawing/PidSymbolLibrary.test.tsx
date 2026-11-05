import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import masterSheet from '../../../public/pid-symbols/symbol-master.svg?raw';
import { PID_SYMBOL_CATEGORIES, PID_SYMBOL_MASTER_SHEET_PATH, PID_SYMBOL_TYPES, PidSymbolShape } from './PidSymbolLibrary';

describe('PidSymbolLibrary', () => {
  test('covers semantic equipment families with recolorable vector symbols', () => {
    const requiredTypes = [
      'pump',
      'vertical_pump',
      'compressor',
      'blower',
      'cooling_tower',
      'fan',
      'tank',
      'column',
      'reactor',
      'mixer',
      'filter',
      'heat_exchanger',
      'air_handler',
      'terminal_unit',
      'drive',
      'chiller',
      'boiler',
      'check_valve',
      'globe_valve',
      'ball_valve',
      'butterfly_valve',
      'plug_valve',
      'needle_valve',
      'diaphragm_valve',
      'solenoid_valve',
      'three_way_valve',
      'angle_valve',
      'dryer',
      'flow_meter',
      'flow_transmitter',
      'gate_valve',
      'gauge',
      'pressure_indicator',
      'pressure_transmitter',
      'temperature_indicator',
      'temperature_transmitter',
      'level_indicator',
      'level_transmitter',
      'analyzer',
      'controller',
      'motor',
      'reducer',
      'flange',
      'blind_flange',
      'cap',
      'expansion_joint',
      'flexible_connector',
      'steam_trap',
      'pid_signal',
      'pid_data',
      'pid_pneumatic',
      'pid_electric',
      'pid_hydraulic',
      'pid_mechanical',
      'pid_capillary',
      'pid_heat_trace',
      'junction',
      'drain',
      'backflow_preventer',
      'water_meter',
      'rotary_pump',
      'centrifugal_pump',
      'centrifugal_fan',
      'cyclone',
      'correcting_element',
      'io_point',
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
      'hand_switch',
      'limit_switch',
      'position_switch',
      'local_instrument',
      'panel_instrument',
      'flanged_valve',
      'reducing_valve',
      'wedge_valve',
      'normally_open_valve',
      'normally_closed_valve',
      'fail_open_valve',
      'fail_closed_valve',
      'balancing_valve',
      'double_check_valve',
      'backpressure_valve',
      'powered_valve',
      'pressure_relief_valve',
      'relief_angle_valve',
      'pneumatic_actuator',
      'electric_actuator',
      'handwheel_actuator',
      'tee',
      'elbow',
      'cross',
      'union',
      'concentric_reducer',
      'eccentric_reducer',
      'pipe_break',
      'flexible_hose',
      'expansion_loop',
      'orifice_plate',
      'spectacle_blind',
      'y_strainer',
      'relief_valve',
      'skid',
      'separator',
      'coil',
      'panel',
      'strainer',
      'vessel',
      'instrument',
      'valve',
      'offpage',
      'flow_arrow',
      'open_tank',
      'closed_tank',
      'covered_tank',
      'plate_heat_exchanger',
      'patch_panel',
      'control_panel',
      'computer_monitor',
      'lcd_monitor',
      'dashpot_piston',
      'pressure_sensor',
      'reference_circle',
      'tag_circle',
      'tag_square',
      'circuit_breaker',
      'disconnect_switch',
      'ejector',
      'expansion_bellows',
      'flame_arrester',
      'hopper',
      'horizontal_vessel',
      'knife_gate_valve',
      'line_blind',
      'pipe_anchor',
      'plc',
      'pressure_regulator',
      'rupture_disk',
      'sample_point',
      'sight_glass',
      'silencer',
      'spray_nozzle',
      'terminal_block',
      'transformer',
      'vent',
      'vertical_vessel',
      'vfd',
      'pid_pneumatic_binary',
      'pid_electric_binary',
      'pid_electromagnetic',
      'pid_heated_cooled',
      'differential_pressure_transmitter',
      'pressure_switch',
      'temperature_switch',
      'flow_switch',
      'level_switch',
      'recorder',
      'alarm',
      'indicator_light',
      'pinch_valve',
      'piston_valve',
      'float_valve',
      'safety_valve',
      'vacuum_breaker',
      'foot_valve',
      'bag_filter',
      'cartridge_filter',
      'centrifugal_separator',
      'tank_mixer',
      'chemical_tote',
      'drum',
      'conveyor',
      'scale',
      'damper',
      'duct_transition',
      'fuse',
      'relay',
      'contactor',
      'motor_starter',
      'panelboard',
      'ground',
      'cable_tray',
      'ups',
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
    ];

    expect(PID_SYMBOL_TYPES).toEqual(expect.arrayContaining(requiredTypes));
  });

  test('organizes every symbol into one stencil category', () => {
    expect(PID_SYMBOL_CATEGORIES.map((category) => category.label)).toEqual([
      'Instruments',
      'Valves',
      'Equipment',
      'Fittings / Continuations',
      'Signal / Line Types',
      'Electrical / Controls',
      'Actuators / Accessories',
    ]);

    const categorized = PID_SYMBOL_CATEGORIES.flatMap((category) => category.types);
    expect(new Set(categorized)).toEqual(new Set(PID_SYMBOL_TYPES));
    expect(categorized).toHaveLength(PID_SYMBOL_TYPES.length);
  });

  test('renders a reusable vector symbol pack primitive with system color', () => {
    render(
      <svg>
        <PidSymbolShape
          bounds={{ x: 10, y: 20, width: 42, height: 28 }}
          fill="#ffffff"
          opacity={1}
          orientation="horizontal"
          stroke="#ea700d"
          strokeWidth={1.1}
          symbolType="compressor"
        />
      </svg>,
    );

    const symbol = screen.getByTestId('pid-symbol-compressor');
    expect(symbol).toHaveAttribute('data-symbol-registry', 'recreation-vector-pack');
    expect(symbol).toHaveAttribute('stroke', '#ea700d');
    expect(symbol.querySelectorAll('path,line,circle,rect,ellipse,polygon').length).toBeGreaterThan(3);
  });

  test('renders newly mined stencil variants as real shapes', () => {
    const newSymbols = [
      'powered_valve',
      'plate_heat_exchanger',
      'closed_tank',
      'centrifugal_fan',
      'pid_electromagnetic',
      'knife_gate_valve',
      'pressure_regulator',
      'sight_glass',
      'horizontal_vessel',
      'plc',
      'differential_pressure_transmitter',
      'pinch_valve',
      'tank_mixer',
      'bag_filter',
      'motor_starter',
      'duplex_strainer',
      'static_mixer',
      'calibration_column',
      'safety_shower',
      'fire_damper',
      'junction_box',
    ];

    render(
      <svg>
        {newSymbols.map((symbolType, index) => (
          <PidSymbolShape
            key={symbolType}
            bounds={{ x: 10 + index * 60, y: 20, width: 44, height: 34 }}
            fill="#ffffff"
            opacity={1}
            stroke="#2255aa"
            strokeWidth={1.2}
            symbolType={symbolType}
          />
        ))}
      </svg>,
    );

    for (const symbolType of newSymbols) {
      const symbol = screen.getByTestId(`pid-symbol-${symbolType}`);
      expect(symbol).toHaveAttribute('data-symbol-registry', 'recreation-vector-pack');
      expect(symbol.querySelectorAll('path,line,circle,rect,ellipse,polygon').length).toBeGreaterThan(1);
    }
  });

  test('renders every exposed stencil as concrete vector geometry', () => {
    const { container } = render(
      <svg>
        {PID_SYMBOL_TYPES.map((symbolType, index) => (
          <PidSymbolShape
            key={symbolType}
            bounds={{ x: 10 + (index % 18) * 54, y: 20 + Math.floor(index / 18) * 44, width: 42, height: 30 }}
            fill="#ffffff"
            opacity={1}
            stroke="#334155"
            strokeWidth={1.1}
            symbolType={symbolType}
          />
        ))}
      </svg>,
    );

    // Index the rendered symbols in one pass. 226 separate attribute-selector lookups
    // take ~1.5 s in jsdom on their own and pushed this test past the 5 s default.
    const symbolsByTestId = new Map(
      Array.from(container.querySelectorAll('[data-testid^="pid-symbol-"]'), (node) => [node.getAttribute('data-testid'), node]),
    );
    for (const symbolType of PID_SYMBOL_TYPES) {
      const symbol = symbolsByTestId.get(`pid-symbol-${symbolType}`);
      expect(symbol, `${symbolType} should render`).toBeDefined();
      expect(symbol?.getAttribute('data-symbol-registry')).toBe('recreation-vector-pack');
      const selfIsGeometry = symbol?.matches('path,line,circle,rect,ellipse,polygon,text') ? 1 : 0;
      expect(
        selfIsGeometry + (symbol?.querySelectorAll('path,line,circle,rect,ellipse,polygon,text').length ?? 0),
        `${symbolType} should render visible vector geometry`,
      ).toBeGreaterThan(0);
    }
  });

  test('ships a master SVG sheet for every symbol type exposed in the app', () => {
    expect(PID_SYMBOL_MASTER_SHEET_PATH).toBe('/pid-symbols/symbol-master.svg');
    for (const symbolType of PID_SYMBOL_TYPES) {
      expect(masterSheet).toContain(`id="${symbolType}"`);
      expect(masterSheet).toContain(`href="#${symbolType}"`);
    }
  });
});
