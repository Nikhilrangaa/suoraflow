/**
 * RoughCutPanel — generate a rough-cut timeline from a script.
 *
 * The user pastes a script, each paragraph ("beat") is matched against the
 * project's footage (transcript + visual embeddings, optionally reranked by
 * Claude), and the matches are assembled into a new timeline. The per-beat
 * match report is rendered below the form.
 */
import { useState } from "react";
import { api, BeatMatch, RoughCutResponse } from "../lib/api";

interface RoughCutPanelProps {
  projectId: string;
  hasReadyAssets: boolean;
  onTimelineCreated: (timelineId: string) => void;
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function BeatRow({ beat }: { beat: BeatMatch }) {
  return (
    <li className="border border-gray-100 rounded-lg p-3 flex items-start gap-3">
      <span className="text-xs font-mono text-gray-400 w-6 text-right shrink-0 pt-0.5">
        {beat.index + 1}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-700">{beat.beat_text}</p>
        {beat.matched ? (
          <div className="flex items-center gap-2 flex-wrap mt-1 text-xs">
            <span
              className={`px-1.5 py-0.5 rounded font-medium ${
                beat.source === "visual"
                  ? "bg-purple-50 text-purple-700"
                  : "bg-indigo-50 text-indigo-700"
              }`}
            >
              {beat.source === "visual" ? "visual" : "spoken"}
            </span>
            <span className="text-gray-500 truncate">{beat.asset_filename}</span>
            {beat.start !== null && beat.end !== null && (
              <span className="font-mono text-indigo-600">
                {formatTime(beat.start)}–{formatTime(beat.end)}
              </span>
            )}
            {beat.score !== null && (
              <span className="text-gray-400">score {beat.score.toFixed(2)}</span>
            )}
          </div>
        ) : (
          <p className="mt-1 text-xs text-amber-600">
            No match — nothing in the footage fits this beat.
          </p>
        )}
      </div>
    </li>
  );
}

export default function RoughCutPanel({
  projectId,
  hasReadyAssets,
  onTimelineCreated,
}: RoughCutPanelProps) {
  const [script, setScript] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RoughCutResponse | null>(null);

  const generate = () => {
    if (!script.trim() || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    api.projects
      .generateRoughCut(projectId, script, name.trim() || undefined)
      .then((res) => {
        setResult(res);
        onTimelineCreated(res.timeline.id);
      })
      .catch((err: unknown) => {
        setError(
          err instanceof Error ? err.message : "Rough cut generation failed",
        );
      })
      .finally(() => setBusy(false));
  };

  const matchedCount = result?.beats.filter((b) => b.matched).length ?? 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">
        Rough Cut from Script
      </h2>

      <textarea
        value={script}
        onChange={(e) => setScript(e.target.value)}
        placeholder={
          "Paste your script here. Each paragraph becomes a beat that gets matched to footage…"
        }
        rows={5}
        disabled={busy}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
          focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
          disabled:opacity-50 resize-y"
      />

      <div className="flex items-center gap-3 mt-3">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Timeline name (optional)"
          disabled={busy}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm
            focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
            disabled:opacity-50"
        />
        <button
          onClick={generate}
          disabled={busy || !script.trim() || !hasReadyAssets}
          className="px-4 py-2 text-sm font-semibold bg-indigo-600 text-white
            rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors
            shrink-0"
        >
          {busy ? "Generating…" : "Generate"}
        </button>
      </div>

      {!hasReadyAssets && (
        <p className="mt-2 text-xs text-gray-400">
          Upload and process at least one asset before generating a rough cut.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {result && (
        <div className="mt-4">
          <div className="flex items-center gap-2 mb-2 text-xs text-gray-500">
            <span>
              {matchedCount} of {result.beats.length} beat
              {result.beats.length !== 1 ? "s" : ""} matched
            </span>
            <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
              {result.method === "llm" ? "Claude rerank" : "embedding match"}
            </span>
          </div>
          <ol className="space-y-2">
            {result.beats.map((beat) => (
              <BeatRow key={beat.index} beat={beat} />
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
