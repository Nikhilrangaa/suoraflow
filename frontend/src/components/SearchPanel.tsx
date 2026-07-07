/**
 * SearchPanel — semantic search over a project's transcripts.
 * Results are ranked chunks with timestamps; clicking one opens the asset
 * at that moment.
 */
import { useState } from "react";
import { api, SearchResult, VisualSearchResult } from "../lib/api";

interface SearchPanelProps {
  projectId: string;
  hasReadyAssets: boolean;
  onOpenResult: (assetId: string, t: number) => void;
  onAddToTimeline?: (result: SearchResult) => void;
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function SearchPanel({
  projectId,
  hasReadyAssets,
  onOpenResult,
  onAddToTimeline,
}: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [visualResults, setVisualResults] = useState<VisualSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setError(null);
    api.projects
      .search(projectId, q)
      .then((res) => {
        setResults(res.results);
        setVisualResults(res.visual_results ?? []);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Search failed");
        setResults(null);
        setVisualResults([]);
      })
      .finally(() => setSearching(false));
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">
        Search Footage by Meaning
      </h2>
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='e.g. "drone footage of the sunrise" or "discussion about the budget"'
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
        >
          {searching ? "Searching..." : "Search"}
        </button>
      </form>

      {!hasReadyAssets && (
        <p className="text-xs text-gray-400 mt-2">
          Search becomes available once at least one asset finishes processing.
        </p>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {results !== null && (
        <div className="mt-4">
          {results.length === 0 && visualResults.length === 0 ? (
            <p className="text-sm text-gray-400">
              No matches. Try different phrasing — search is semantic, not keyword-based.
            </p>
          ) : results.length === 0 ? null : (
            <>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Spoken matches
            </h3>
            <ul className="space-y-2">
              {results.map((r, i) => (
                <li
                  key={r.chunk_id}
                  className="border border-gray-100 rounded-lg p-3 hover:border-indigo-200 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <button
                      onClick={() => onOpenResult(r.asset_id, r.start)}
                      className="flex-1 min-w-0 text-left"
                    >
                      <div className="flex items-center gap-2 flex-wrap text-xs text-gray-400 mb-1">
                        <span className="font-semibold text-gray-500">#{i + 1}</span>
                        <span className="truncate">{r.asset_filename}</span>
                        <span className="font-mono text-indigo-600">
                          {formatTime(r.start)}–{formatTime(r.end)}
                        </span>
                        <span
                          className="bg-indigo-50 text-indigo-700 rounded px-1.5 py-0.5 font-medium"
                          title="Cosine similarity"
                        >
                          {(r.score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="text-sm text-gray-800 line-clamp-2">{r.text}</p>
                    </button>
                    {onAddToTimeline && (
                      <button
                        onClick={() => onAddToTimeline(r)}
                        className="shrink-0 text-xs px-2 py-1 rounded-lg border border-indigo-200 text-indigo-700 hover:bg-indigo-50 transition-colors"
                        title="Add this clip to the timeline"
                      >
                        + Timeline
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            </>
          )}

          {/* Visual matches — CLIP over sampled frames (what's ON SCREEN) */}
          {visualResults.length > 0 && (
            <div className="mt-5">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Visual matches
                <span className="ml-2 font-normal normal-case text-gray-400">
                  what&apos;s on screen, no speech needed
                </span>
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {visualResults.map((v) => (
                  <button
                    key={v.frame_id}
                    onClick={() => onOpenResult(v.asset_id, v.timestamp)}
                    className="group text-left rounded-lg border border-gray-100 hover:border-indigo-300 overflow-hidden transition-colors"
                    title={`${v.asset_filename} at ${formatTime(v.timestamp)}`}
                  >
                    <img
                      src={api.assets.frameUrl(v.asset_id, v.frame_index)}
                      alt={`Frame at ${formatTime(v.timestamp)}`}
                      loading="lazy"
                      className="w-full aspect-video object-cover bg-gray-100"
                    />
                    <div className="px-2 py-1.5 flex items-center justify-between text-xs">
                      <span className="font-mono text-indigo-600">
                        {formatTime(v.timestamp)}
                      </span>
                      <span
                        className="bg-indigo-50 text-indigo-700 rounded px-1.5 py-0.5 font-medium"
                        title="CLIP similarity"
                      >
                        {(v.score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
