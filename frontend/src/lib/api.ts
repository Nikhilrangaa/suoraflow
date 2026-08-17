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
  speech_ratio: number | null;
  vad_segment_count: number | null;
  created_at: string;
}

export interface AssetStatus {
  id: string;
  status: string;
  error_message: string | null;
}

export interface TranscriptSegment {
  id: string;
  seg_index: number;
  start: number;
  end: number;
  text: string;
  speaker: string;
}

export interface Transcript {
  asset_id: string;
  status: string;
  segments: TranscriptSegment[];
}

export interface Waveform {
  asset_id: string;
  peaks: number[];
  duration: number;
}

export interface SearchResult {
  asset_id: string;
  asset_filename: string;
  media_type: string;
  chunk_id: string;
  text: string;
  start: number;
  end: number;
  score: number;
}

export interface VisualSearchResult {
  asset_id: string;
  asset_filename: string;
  frame_id: string;
  frame_index: number;
  timestamp: number;
  score: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  visual_results: VisualSearchResult[];
  total: number;
}

export interface Clip {
  id: string;
  project_id: string;
  asset_id: string;
  asset_filename: string;
  start: number;
  end: number;
  label: string;
  created_at: string;
}

export interface TimelineItem {
  id: string;
  position: number;
  clip: Clip;
}

export interface Timeline {
  id: string;
  project_id: string;
  name: string;
  created_at: string;
  items: TimelineItem[];
  total_duration: number;
}

export interface BeatMatch {
  index: number;
  beat_text: string;
  matched: boolean;
  source: "transcript" | "visual" | null;
  asset_id: string | null;
  asset_filename: string | null;
  start: number | null;
  end: number | null;
  score: number | null;
  method: "llm" | "embedding";
}

export interface RoughCutResponse {
  timeline: Timeline;
  beats: BeatMatch[];
  method: "llm" | "embedding";
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
    search: (id: string, query: string, limit = 10): Promise<SearchResponse> =>
      request<SearchResponse>(`/api/projects/${id}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit }),
      }),
    createClip: (
      id: string,
      clip: { asset_id: string; start: number; end: number; label: string },
    ): Promise<Clip> =>
      request<Clip>(`/api/projects/${id}/clips`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clip),
      }),
    listClips: (id: string): Promise<Clip[]> =>
      request<Clip[]>(`/api/projects/${id}/clips`),
    createTimeline: (id: string, name = "Rough Cut"): Promise<Timeline> =>
      request<Timeline>(`/api/projects/${id}/timelines`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }),
    listTimelines: (id: string): Promise<Timeline[]> =>
      request<Timeline[]>(`/api/projects/${id}/timelines`),
    generateRoughCut: (
      id: string,
      script: string,
      name?: string,
    ): Promise<RoughCutResponse> =>
      request<RoughCutResponse>(`/api/projects/${id}/rough-cut`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(name ? { script, name } : { script }),
      }),
  },

  timelines: {
    get: (id: string): Promise<Timeline> => request<Timeline>(`/api/timelines/${id}`),
    addItem: (id: string, clipId: string): Promise<Timeline> =>
      request<Timeline>(`/api/timelines/${id}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clip_id: clipId }),
      }),
    moveItem: (id: string, itemId: string, position: number): Promise<Timeline> =>
      request<Timeline>(`/api/timelines/${id}/items/${itemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position }),
      }),
    removeItem: (id: string, itemId: string): Promise<void> =>
      request<void>(`/api/timelines/${id}/items/${itemId}`, { method: "DELETE" }),
    exportUrl: (id: string, format: "json" | "csv"): string =>
      `${API_BASE}/api/timelines/${id}/export?format=${format}`,
  },

  assets: {
    get: (id: string): Promise<Asset> => request<Asset>(`/api/assets/${id}`),
    status: (id: string): Promise<AssetStatus> =>
      request<AssetStatus>(`/api/assets/${id}/status`),
    transcript: (id: string): Promise<Transcript> =>
      request<Transcript>(`/api/assets/${id}/transcript`),
    waveform: (id: string): Promise<Waveform> =>
      request<Waveform>(`/api/assets/${id}/waveform`),
    mediaUrl: (id: string): string => `${API_BASE}/api/assets/${id}/media`,
    frameUrl: (id: string, frameIndex: number): string =>
      `${API_BASE}/api/assets/${id}/frames/${frameIndex}`,
    delete: (id: string): Promise<void> =>
      request<void>(`/api/assets/${id}`, { method: "DELETE" }),
  },
};
