import type {
  DrawingDocument,
  DrawingExportResult,
  DrawingGraph,
  HierarchyTemplate,
  JobStatus,
  LayoutOption,
  PreflightReview,
  Project,
  ServiceInfo,
  StitchJobResult,
} from '../types';
import { normalizeProject } from '../types';

const DEFAULT_BROWSER_API = import.meta.env.VITE_RECREATION_API_URL ?? 'http://127.0.0.1:8765';

async function invokeTauri<T>(command: string, args?: Record<string, unknown>): Promise<T | null> {
  if (!('__TAURI_INTERNALS__' in window)) {
    return null;
  }
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(command, args);
}

export async function startService(): Promise<ServiceInfo> {
  const tauriInfo = await invokeTauri<ServiceInfo>('start_project_service');
  if (tauriInfo) {
    return { ...tauriInfo, mode: 'tauri' };
  }
  return { baseUrl: DEFAULT_BROWSER_API, port: Number(new URL(DEFAULT_BROWSER_API).port), dataDir: '.recreation-data', mode: 'browser' };
}

export async function stopService(): Promise<void> {
  await invokeTauri<void>('stop_project_service');
}

export async function selectImportFiles(): Promise<string[]> {
  const selected = await invokeTauri<string[]>('select_import_files');
  return selected ?? [];
}

export async function openSourceEvidence(projectId: string, evidenceId: string): Promise<void> {
  await invokeTauri<void>('open_source_evidence', { projectId, evidenceId });
}

export interface ImportFileSelection {
  path: string;
  pages?: number[];
}

export interface PdfPreviewPage {
  page: number;
  width: number;
  height: number;
  thumbnailUrl: string;
}

export interface PdfPreview {
  path: string;
  name: string;
  pageCount: number;
  pages: PdfPreviewPage[];
}

export class RecreationApi {
  constructor(private readonly baseUrl: string) {}

  async health(): Promise<{ ok: boolean }> {
    return this.request('/health');
  }

  async listProjects(): Promise<Project[]> {
    const raw: Record<string, unknown>[] = await this.request('/projects');
    return raw.map(normalizeProject);
  }

  async createProject(name: string): Promise<Project> {
    const raw = await this.request<Record<string, unknown>>('/projects', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
    return normalizeProject(raw);
  }

  async importFiles(projectId: string, filesOrPaths: string[] | ImportFileSelection[]): Promise<{ files: unknown[] }> {
    const body =
      filesOrPaths.length > 0 && typeof filesOrPaths[0] === 'string'
        ? { paths: filesOrPaths }
        : { files: filesOrPaths };
    return this.request(`/projects/${projectId}/imports`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async previewPdf(path: string, dpi = 54): Promise<PdfPreview> {
    return this.request(`/pdf-preview?path=${encodeURIComponent(path)}&dpi=${dpi}`);
  }

  pdfPreviewPageImageUrl(path: string, page: number, dpi = 54): string {
    return `${this.baseUrl}/pdf-preview/page-image?path=${encodeURIComponent(path)}&page=${page}&dpi=${dpi}`;
  }

  async runPreflight(projectId: string): Promise<PreflightReview> {
    return this.request(`/projects/${projectId}/preflight`, { method: 'POST' });
  }

  async getPreflight(projectId: string): Promise<PreflightReview> {
    return this.request(`/projects/${projectId}/preflight`);
  }

  async confirmPreflight(projectId: string, review: PreflightReview): Promise<PreflightReview> {
    return this.request(`/projects/${projectId}/preflight`, {
      method: 'PUT',
      body: JSON.stringify({ payload: review }),
    });
  }

  async listHierarchyTemplates(): Promise<HierarchyTemplate[]> {
    return this.request('/hierarchy-templates');
  }

  async saveHierarchyTemplate(name: string, review: PreflightReview): Promise<HierarchyTemplate> {
    return this.request('/hierarchy-templates', {
      method: 'POST',
      body: JSON.stringify({ name, review }),
    });
  }

  async startExtract(projectId: string): Promise<{ jobId: string }> {
    return this.request(`/projects/${projectId}/jobs/extract`, { method: 'POST' });
  }

  async startStitch(projectId: string): Promise<StitchJobResult> {
    return this.request(`/projects/${projectId}/jobs/stitch`, { method: 'POST' });
  }

  async getJob(jobId: string): Promise<JobStatus> {
    return this.request(`/jobs/${jobId}`);
  }

  subscribeJobEvents(jobId: string, onEvent: (event: JobStatus) => void, onDone: () => void): () => void {
    const source = new EventSource(`${this.baseUrl}/jobs/${jobId}/events`);
    let closed = false;

    const handleMessage = (event: MessageEvent): void => {
      try {
        const data = JSON.parse(event.data) as Record<string, unknown>;
        if (data.id && data.status) {
          onEvent(data as unknown as JobStatus);
        }
      } catch {
        // heartbeat or malformed
      }
    };

    source.addEventListener('status', handleMessage);
    source.addEventListener('completed', (event: MessageEvent) => {
      handleMessage(event);
      cleanup();
      onDone();
    });
    source.addEventListener('failed', (event: MessageEvent) => {
      handleMessage(event);
      cleanup();
      onDone();
    });
    source.addEventListener('error', () => {
      cleanup();
      onDone();
    });

    function cleanup(): void {
      if (closed) return;
      closed = true;
      source.close();
    }

    return cleanup;
  }

  async getGraph(projectId: string): Promise<DrawingGraph> {
    return this.request(`/projects/${projectId}/graph`);
  }

  async listLayoutOptions(projectId: string): Promise<LayoutOption[]> {
    return this.request(`/projects/${projectId}/layout-options`);
  }

  async getDrawing(projectId: string, drawingId: string): Promise<DrawingDocument> {
    return this.request(`/projects/${projectId}/drawings/${drawingId}`);
  }

  async updateDrawing(projectId: string, drawing: DrawingDocument): Promise<DrawingDocument> {
    return this.request(`/projects/${projectId}/drawings/${drawing.id}`, {
      method: 'PUT',
      body: JSON.stringify(drawing),
    });
  }

  async updateLayout(projectId: string, graph: Pick<DrawingGraph, 'nodes' | 'edges'>): Promise<DrawingGraph> {
    return this.request(`/projects/${projectId}/layout`, {
      method: 'PUT',
      body: JSON.stringify({
        nodes: graph.nodes.map((node) => ({ id: node.id, layout: node.layout, locked: node.locked })),
        edges: graph.edges.map((edge) => ({ id: edge.id, waypoints: edge.waypoints })),
      }),
    });
  }

  async resolveReview(projectId: string, itemId: string, resolution: Record<string, unknown>): Promise<unknown> {
    return this.request(`/projects/${projectId}/review/${itemId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ resolvedBy: 'user', resolution }),
    });
  }

  async updateNode(projectId: string, nodeId: string, updates: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request(`/projects/${projectId}/nodes/${nodeId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  }

  async deleteNode(projectId: string, nodeId: string): Promise<{ deleted: string }> {
    return this.request(`/projects/${projectId}/nodes/${nodeId}`, { method: 'DELETE' });
  }

  async updateEdge(projectId: string, edgeId: string, updates: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request(`/projects/${projectId}/edges/${edgeId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  }

  async export(projectId: string, type: 'svg' | 'pdf' | 'xlsx'): Promise<{ path: string; type: string }> {
    return this.request(`/projects/${projectId}/exports/${type}`, { method: 'POST' });
  }

  async exportDrawing(projectId: string, drawingId: string, type: 'svg' | 'pdf'): Promise<DrawingExportResult> {
    return this.request(`/projects/${projectId}/drawings/${drawingId}/exports/${type}`, { method: 'POST' });
  }

  async listSources(projectId: string): Promise<Array<{ id: string; name: string; pageCount: number }>> {
    return this.request(`/projects/${projectId}/sources`);
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...init.headers,
      },
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${response.status} ${response.statusText}: ${detail}`);
    }
    return response.json() as Promise<T>;
  }
}
