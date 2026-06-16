/**
 * api.ts — Typed API client for SuoraFlow backend.
 * All calls go through the VITE_API_URL base.
 */

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  asset_count: number;
}

export interface ProjectList {
  projects: Project[];
  total: number;
}

export interface Asset {
  id: string;
  project_id: string;
  original_filename: string;
  media_type: string;
  ext: string;
  size_bytes: number;
  status: string;
  error_message: string | null;
  sample_rate: number | null;
  channels: number | null;
  audio_codec: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  created_at: string;
}

export interface HealthData {
  status: string;
  db: string;
  redis: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore json parse failure
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const api = {
  health: (): Promise<HealthData> => request<HealthData>("/health"),

  projects: {
    list: (): Promise<ProjectList> => request<ProjectList>("/api/projects"),
    get: (id: string): Promise<Project> => request<Project>(`/api/projects/${id}`),
    create: (name: string, description: string): Promise<Project> =>
      request<Project>("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      }),
    delete: (id: string): Promise<void> =>
      request<void>(`/api/projects/${id}`, { method: "DELETE" }),
    listAssets: (id: string): Promise<Asset[]> =>
      request<Asset[]>(`/api/projects/${id}/assets`),
    uploadAsset: (id: string, file: File): Promise<Asset> => {
      const form = new FormData();
      form.append("file", file);
      return request<Asset>(`/api/projects/${id}/assets/upload`, {
        method: "POST",
        body: form,
      });
    },
  },

  assets: {
    get: (id: string): Promise<Asset> => request<Asset>(`/api/assets/${id}`),
    delete: (id: string): Promise<void> =>
      request<void>(`/api/assets/${id}`, { method: "DELETE" }),
  },
};
