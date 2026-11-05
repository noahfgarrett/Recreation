export type NodeKind =
  | 'equipment'
  | 'instrument'
  | 'valve'
  | 'panel'
  | 'junction_box'
  | 'off_page_connector'
  | 'cable_endpoint'
  | 'motor'
  | 'breaker'
  | 'transformer'
  | 'vfd'
  | 'mcc'
  | 'switchgear'
  | 'unknown';

export type EdgeKind = 'pipe' | 'instrument_signal' | 'cable' | 'conduit' | 'continuation' | 'power_feed' | 'control_wire' | 'unknown';

export interface Bounds {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SourceEvidence {
  id: string;
  sourceFileId: string;
  page: number;
  bounds: Bounds | null;
  text: string;
  confidence: number;
}

export interface Port {
  id: string;
  label: string;
  side: 'top' | 'right' | 'bottom' | 'left';
}

export interface Layout {
  x: number;
  y: number;
  width: number;
  height: number;
  groupId?: string | null;
  waypoints?: Array<{ x: number; y: number }>;
}

export interface GraphNode {
  id: string;
  kind: NodeKind;
  tag: string;
  symbolId: string | null;
  ports: Port[];
  sourceEvidence: SourceEvidence[];
  confidence: number;
  locked: boolean;
  layout: Layout;
}

export interface GraphEdge {
  id: string;
  kind: EdgeKind;
  sourcePort: string;
  targetPort: string;
  label: string;
  lineOrCableId: string | null;
  waypoints: Array<{ x: number; y: number }>;
  continuationRefs: string[];
  sourceEvidence: SourceEvidence[];
  confidence: number;
  status: 'confirmed' | 'needs_review' | 'inferred';
}

export interface ReviewItem {
  id: string;
  type:
    | 'symbol_confirmation'
    | 'continuation_match'
    | 'low_confidence_tag'
    | 'unconnected_item'
    | 'export_warning';
  candidates: Array<Record<string, unknown>>;
  recommendedAction: string;
  evidence: SourceEvidence[];
  resolvedBy: string | null;
  resolution: Record<string, unknown> | null;
  status: 'open' | 'resolved' | 'ignored';
}

export interface DrawingGraph {
  projectId: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  reviewItems: ReviewItem[];
}

export type DisciplineName =
  | 'Electrical'
  | 'Process / P&ID'
  | 'Mechanical'
  | 'Mechanical Dry'
  | 'Mechanical Wet'
  | 'Plumbing'
  | 'Instrumentation & Control'
  | 'Security'
  | 'Fire Alarm'
  | 'Fire Protection'
  | 'Life Safety Services'
  | 'Telecom / Low Voltage'
  | 'Controls / BAS'
  | 'CSA'
  | 'General / Reference'
  | 'Mixed Package'
  | 'Unknown';

export type PageRoleName =
  | 'legend_reference'
  | 'abbreviations'
  | 'general_notes'
  | 'sheet_index'
  | 'one_line'
  | 'riser'
  | 'pid'
  | 'plan_view'
  | 'detail_sheet'
  | 'panel_schedule'
  | 'equipment_schedule'
  | 'line_list'
  | 'instrument_index'
  | 'loop_sheet'
  | 'cable_schedule'
  | 'io_schedule'
  | 'control_panel'
  | 'fire_alarm_riser'
  | 'security_riser'
  | 'plumbing_riser'
  | 'mechanical_schedule'
  | 'csa_plan_detail'
  | 'vendor_drawing'
  | 'unknown';

export interface PageRoleAssignment {
  sourceFileId: string;
  page: number;
  role: PageRoleName;
  confidence: number;
  reason: string;
  title?: string;
  sheetNumber?: string;
}

export interface PreflightPageSelection {
  sourceFileId: string;
  page: number;
}

export interface PreflightSourceFile {
  id: string;
  name: string;
  pageCount: number;
}

export interface PreflightPagePreviewTarget {
  sourceFileId: string;
  sourceFileName: string;
  page: number;
  totalPages: number;
}

export interface PreflightReview {
  projectId: string;
  status: 'draft' | 'confirmed';
  preflightSchemaVersion?: number;
  disciplines: DisciplineName[];
  disciplineConfidence: number;
  legendPages: number[];
  legendConfidence: number;
  pageRoles: PageRoleAssignment[];
  selectedPages?: PreflightPageSelection[];
  tableFamilies: string[];
  suggestedTemplateIds: string[];
  appliedTemplateId: string | null;
  warnings: string[];
}

export type ImportWorkflowMode = 'hierarchy' | 'combiner' | 'both';

export interface HierarchyTemplate {
  id: string;
  name: string;
  disciplines: DisciplineName[];
  description: string;
  confidence?: number;
  payload?: Record<string, unknown>;
}

export type HierarchyViewId =
  | 'electrical_power'
  | 'commissioning_dependencies'
  | 'process_flow'
  | 'mechanical_system'
  | 'ic_loop'
  | 'security_device'
  | 'fire_life_safety'
  | 'plumbing_fire_protection'
  | 'equipment_asset'
  | 'location_area'
  | 'source_document'
  | 'overview_export';

export interface RulebookSummary {
  projectId: string;
  disciplines: DisciplineName[];
  legendPages: number[];
  acronymMap: Record<string, string>;
  symbolRules: Array<Record<string, unknown>>;
  tagRules: Array<Record<string, unknown>>;
  suppressionRules: Array<Record<string, unknown>>;
  sourceEvidence: Array<Record<string, unknown>>;
  warnings: string[];
}

export interface HierarchyViewPayload {
  id: HierarchyViewId;
  label: string;
  discipline: DisciplineName;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
}

export type DrawingMetricValue = number | string | boolean | string[] | null;

export interface DrawingStyle {
  stroke: string;
  fill: string;
  strokeWidth: number;
  opacity: number;
  dash?: number[] | null;
  fontSize?: number | null;
  fontFamily?: string | null;
}

export interface DrawingPoint {
  x: number;
  y: number;
}

export interface DrawingBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type DrawingObjectKind = 'pipe' | 'label' | 'symbol' | 'region' | 'source_fragment' | 'connector';

export interface DrawingObject {
  id: string;
  kind: DrawingObjectKind;
  label: string;
  points: DrawingPoint[];
  bounds: DrawingBounds;
  style: DrawingStyle;
  sourceEvidenceIds: string[];
  locked?: boolean;
  groupId?: string | null;
  metadata?: Record<string, unknown>;
}

export interface TextSpan {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  color?: string | null;
}

export interface VectorSegment {
  id: string;
  kind: 'line' | 'polyline' | 'curve' | 'rect' | 'unknown';
  points: DrawingPoint[];
  bounds: DrawingBounds;
  stroke?: string | null;
  strokeWidth?: number | null;
  dashed: boolean;
}

export interface PageEvidence {
  id: string;
  sourceFileId: string;
  page: number;
  width: number;
  height: number;
  rotation: number;
  cropBounds: DrawingBounds;
  textSpans: TextSpan[];
  vectorCount: number;
  vectorSegments?: VectorSegment[];
  metadata?: Record<string, unknown>;
}

export interface DrawingDocument {
  id: string;
  projectId: string;
  name: string;
  width: number;
  height: number;
  objects: DrawingObject[];
  sourcePages: PageEvidence[];
  styles: Record<string, DrawingStyle>;
  visualQa: Record<string, unknown>;
}

export interface LayoutOption {
  id: string;
  projectId: string;
  drawingId: string;
  name: string;
  description: string;
  score: number;
  metrics: Record<string, DrawingMetricValue>;
  drawingDocument?: DrawingDocument;
}

export interface DrawingExportResult {
  projectId: string;
  drawingId: string;
  path: string;
  type: string;
}

export interface StitchJobResult {
  jobId: string;
}

export interface Project {
  id: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  created_at?: string;
  updated_at?: string;
}

export function normalizeProject(raw: Record<string, unknown>): Project {
  return {
    id: String(raw.id ?? ''),
    name: String(raw.name ?? ''),
    createdAt: String(raw.createdAt ?? raw.created_at ?? ''),
    updatedAt: String(raw.updatedAt ?? raw.updated_at ?? ''),
  };
}

export interface JobStatus {
  id: string;
  name: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface ServiceInfo {
  baseUrl: string;
  port: number;
  dataDir: string;
  mode: 'tauri' | 'browser';
}
