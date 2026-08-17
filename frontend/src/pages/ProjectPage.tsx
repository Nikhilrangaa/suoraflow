/**
 * ProjectPage — show project details, upload assets, list assets.
 */
import { useEffect, useRef, useState } from "react";
import { api, ApiError, Asset, Project } from "../lib/api";
import StatusBadge, { isProcessing } from "../components/StatusBadge";
import SearchPanel from "../components/SearchPanel";
import RoughCutPanel from "../components/RoughCutPanel";
import TimelinePanel, { TimelinePanelHandle } from "../components/TimelinePanel";

// Extensions mirrored from backend allow-list
const ALLOWED_EXTENSIONS =
  ".mp4,.mov,.mkv,.avi,.webm,.mts,.m2ts,.mp3,.wav,.aac,.flac,.ogg,.m4a";

const POLL_MS = 2500;

interface ProjectPageProps {
  projectId: string;
  onBack: () => void;
  onSelectAsset: (assetId: string, t?: number) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProjectPage({ projectId, onBack, onSelectAsset }: ProjectPageProps) {
  const [project, setProject] = useState<Project | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loadingProject, setLoadingProject] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Delete confirm
  const [deletingAssetId, setDeletingAssetId] = useState<string | null>(null);

  // Timeline panel handle (search results are added through it)
  const timelineRef = useRef<TimelinePanelHandle>(null);

  const loadData = () => {
    setLoadingProject(true);
    setError(null);
    Promise.all([
      api.projects.get(projectId),
      api.projects.listAssets(projectId),
    ])
      .then(([proj, assetList]) => {
        setProject(proj);
        setAssets(assetList);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load project");
      })
      .finally(() => setLoadingProject(false));
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Poll asset list while any asset is still processing so status badges live-update
  const anyProcessing = assets.some((a) => isProcessing(a.status));
  useEffect(() => {
    if (!anyProcessing) return;
    const timer = setInterval(() => {
      api.projects
        .listAssets(projectId)
        .then(setAssets)
        .catch(() => {
          /* transient poll errors are ignored */
        });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [anyProcessing, projectId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploading(true);
    api.projects
      .uploadAsset(projectId, file)
      .then((asset) => {
        setAssets((prev) => [asset, ...prev]);
        setProject((prev) =>
          prev ? { ...prev, asset_count: prev.asset_count + 1 } : prev,
        );
        // Reset file input
        if (fileRef.current) fileRef.current.value = "";
      })
      .catch((err: unknown) => {
        let msg = "Upload failed";
        if (err instanceof ApiError) {
          if (err.status === 400) msg = `Invalid file: ${err.message}`;
          else if (err.status === 413) msg = `File too large: ${err.message}`;
          else msg = err.message;
        } else if (err instanceof Error) {
          msg = err.message;
        }
        setUploadError(msg);
        if (fileRef.current) fileRef.current.value = "";
      })
      .finally(() => setUploading(false));
  };

  const handleDeleteAsset = (assetId: string) => {
    api.assets
      .delete(assetId)
      .then(() => {
        setAssets((prev) => prev.filter((a) => a.id !== assetId));
        setProject((prev) =>
          prev ? { ...prev, asset_count: Math.max(0, prev.asset_count - 1) } : prev,
        );
        setDeletingAssetId(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to delete asset");
        setDeletingAssetId(null);
      });
  };

  if (loadingProject) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 animate-pulse">Loading project...</p>
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error}</p>
          <button onClick={onBack} className="text-indigo-600 hover:underline text-sm">
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Delete asset confirm modal */}
      {deletingAssetId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Delete Asset?</h2>
            <p className="text-sm text-gray-600 mb-6">
              The file will be permanently removed. This cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeletingAssetId(null)}
                className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteAsset(deletingAssetId)}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            title="Back"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-5 h-5"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"
              />
            </svg>
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{project?.name}</h1>
            {project?.description && (
              <p className="text-sm text-gray-500">{project.description}</p>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto p-6">
        {error && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Semantic search */}
        <SearchPanel
          projectId={projectId}
          hasReadyAssets={assets.some((a) => a.status === "ready")}
          onOpenResult={(assetId, t) => onSelectAsset(assetId, t)}
          onAddToTimeline={(result) => timelineRef.current?.addFromSearchResult(result)}
        />

        {/* Script-to-footage rough cut */}
        <RoughCutPanel
          projectId={projectId}
          hasReadyAssets={assets.some((a) => a.status === "ready")}
          onTimelineCreated={(timelineId) =>
            timelineRef.current?.showTimeline(timelineId)
          }
        />

        {/* Rough-cut timeline */}
        <TimelinePanel
          ref={timelineRef}
          projectId={projectId}
          onOpenClip={(assetId, t) => onSelectAsset(assetId, t)}
        />

        {/* Upload section */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Upload Media</h2>
          <div className="flex items-start gap-4">
            <label className="flex-1">
              <input
                ref={fileRef}
                type="file"
                accept={ALLOWED_EXTENSIONS}
                onChange={handleFileChange}
                disabled={uploading}
                className="block w-full text-sm text-gray-500
                  file:mr-4 file:py-2 file:px-4
                  file:rounded-lg file:border-0
                  file:text-sm file:font-semibold
                  file:bg-indigo-50 file:text-indigo-700
                  hover:file:bg-indigo-100
                  disabled:opacity-50 cursor-pointer"
              />
            </label>
            {uploading && (
              <span className="text-sm text-indigo-600 animate-pulse">Uploading...</span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Accepted: {ALLOWED_EXTENSIONS.split(",").join(", ")}
          </p>
          {uploadError && (
            <p className="mt-2 text-sm text-red-600">{uploadError}</p>
          )}
        </div>

        {/* Assets list */}
        <div>
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
            Assets ({assets.length})
          </h2>

          {assets.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">
              No assets yet. Upload a file above to get started.
            </p>
          ) : (
            <div className="space-y-2">
              {assets.map((asset) => (
                <div
                  key={asset.id}
                  className="bg-white rounded-xl border border-gray-200 p-4 flex items-center justify-between hover:border-indigo-300 transition-colors"
                >
                  <button
                    onClick={() => onSelectAsset(asset.id)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium text-gray-900 text-sm truncate">
                        {asset.original_filename}
                      </p>
                      <StatusBadge status={asset.status} />
                      <span className="text-xs text-gray-400 uppercase">
                        {asset.media_type}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {formatBytes(asset.size_bytes)} &middot; {asset.ext}
                    </p>
                    {asset.error_message && (
                      <p className="text-xs text-red-500 mt-0.5">{asset.error_message}</p>
                    )}
                  </button>
                  <button
                    onClick={() => setDeletingAssetId(asset.id)}
                    className="ml-4 text-gray-400 hover:text-red-500 transition-colors p-1 flex-shrink-0"
                    title="Delete asset"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      className="w-5 h-5"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
                      />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
