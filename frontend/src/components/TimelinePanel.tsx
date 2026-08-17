/**
 * TimelinePanel — the project's rough-cut timeline.
 *
 * Search results are added as clips; items can be reordered (up/down),
 * removed, and the whole timeline exported as JSON or CSV.
 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useState } from "react";
import { api, SearchResult, Timeline } from "../lib/api";

export interface TimelinePanelHandle {
  addFromSearchResult: (result: SearchResult) => void;
  /** Load and display a specific timeline (e.g. a freshly generated rough cut). */
  showTimeline: (timelineId: string) => void;
}

interface TimelinePanelProps {
  projectId: string;
  onOpenClip: (assetId: string, t: number) => void;
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const TimelinePanel = forwardRef<TimelinePanelHandle, TimelinePanelProps>(
  function TimelinePanel({ projectId, onOpenClip }, ref) {
    const [timeline, setTimeline] = useState<Timeline | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);

    useEffect(() => {
      api.projects
        .listTimelines(projectId)
        .then((timelines) => setTimeline(timelines[0] ?? null))
        .catch(() => setTimeline(null))
        .finally(() => setLoading(false));
    }, [projectId]);

    const flashNotice = (msg: string) => {
      setNotice(msg);
      setTimeout(() => setNotice(null), 2500);
    };

    /** Get the project's timeline, creating the default one on first use. */
    const ensureTimeline = useCallback(async (): Promise<Timeline> => {
      if (timeline) return timeline;
      const timelines = await api.projects.listTimelines(projectId);
      if (timelines.length > 0) return timelines[0];
      return api.projects.createTimeline(projectId);
    }, [projectId, timeline]);

    useImperativeHandle(ref, () => ({
      addFromSearchResult: (result: SearchResult) => {
        setBusy(true);
        setError(null);
        (async () => {
          const tl = await ensureTimeline();
          const clip = await api.projects.createClip(projectId, {
            asset_id: result.asset_id,
            start: result.start,
            end: result.end,
            label: result.text.slice(0, 200),
          });
          const updated = await api.timelines.addItem(tl.id, clip.id);
          setTimeline(updated);
          flashNotice("Clip added to timeline");
        })()
          .catch((err: unknown) =>
            setError(err instanceof Error ? err.message : "Failed to add clip"),
          )
          .finally(() => setBusy(false));
      },
      showTimeline: (timelineId: string) => {
        setBusy(true);
        setError(null);
        api.timelines
          .get(timelineId)
          .then((tl) => {
            setTimeline(tl);
            flashNotice("Rough cut added as a new timeline");
          })
          .catch((err: unknown) =>
            setError(err instanceof Error ? err.message : "Failed to load timeline"),
          )
          .finally(() => setBusy(false));
      },
    }));

    const move = (itemId: string, position: number) => {
      if (!timeline || position < 0 || position >= timeline.items.length) return;
      setBusy(true);
      api.timelines
        .moveItem(timeline.id, itemId, position)
        .then(setTimeline)
        .catch((err: unknown) =>
          setError(err instanceof Error ? err.message : "Failed to reorder"),
        )
        .finally(() => setBusy(false));
    };

    const remove = (itemId: string) => {
      if (!timeline) return;
      setBusy(true);
      api.timelines
        .removeItem(timeline.id, itemId)
        .then(() => api.timelines.get(timeline.id))
        .then(setTimeline)
        .catch((err: unknown) =>
          setError(err instanceof Error ? err.message : "Failed to remove item"),
        )
        .finally(() => setBusy(false));
    };

    const hasItems = !!timeline && timeline.items.length > 0;

    return (
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700">
            Timeline{timeline ? ` — ${timeline.name}` : ""}
            {hasItems && (
              <span className="ml-2 text-xs font-normal text-gray-400">
                {timeline.items.length} clip{timeline.items.length !== 1 ? "s" : ""} ·{" "}
                {formatTime(timeline.total_duration)} total
              </span>
            )}
          </h2>
          {hasItems && (
            <div className="flex gap-2">
              <a
                href={api.timelines.exportUrl(timeline.id, "json")}
                className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
                download
              >
                Export JSON
              </a>
              <a
                href={api.timelines.exportUrl(timeline.id, "csv")}
                className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
                download
              >
                Export CSV
              </a>
            </div>
          )}
        </div>

        {notice && (
          <p className="mb-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-1.5">
            {notice}
          </p>
        )}
        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

        {loading ? (
          <p className="text-sm text-gray-400 animate-pulse">Loading timeline...</p>
        ) : !hasItems ? (
          <p className="text-sm text-gray-400">
            No clips yet. Search your footage above and click “+ Timeline” on a result
            to start building a rough cut.
          </p>
        ) : (
          <ol className="space-y-2">
            {timeline.items.map((item, idx) => (
              <li
                key={item.id}
                className="border border-gray-100 rounded-lg p-3 flex items-center gap-3"
              >
                <span className="text-xs font-mono text-gray-400 w-6 text-right shrink-0">
                  {idx + 1}
                </span>
                <button
                  onClick={() => onOpenClip(item.clip.asset_id, item.clip.start)}
                  className="flex-1 min-w-0 text-left"
                  title="Open at this timestamp"
                >
                  <div className="flex items-center gap-2 flex-wrap text-xs text-gray-400">
                    <span className="truncate">{item.clip.asset_filename}</span>
                    <span className="font-mono text-indigo-600">
                      {formatTime(item.clip.start)}–{formatTime(item.clip.end)}
                    </span>
                    <span className="text-gray-400">
                      ({formatTime(item.clip.end - item.clip.start)})
                    </span>
                  </div>
                  {item.clip.label && (
                    <p className="text-sm text-gray-700 line-clamp-1 mt-0.5">
                      {item.clip.label}
                    </p>
                  )}
                </button>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => move(item.id, idx - 1)}
                    disabled={busy || idx === 0}
                    className="p-1 text-gray-400 hover:text-indigo-600 disabled:opacity-30 transition-colors"
                    title="Move up"
                  >
                    ▲
                  </button>
                  <button
                    onClick={() => move(item.id, idx + 1)}
                    disabled={busy || idx === timeline.items.length - 1}
                    className="p-1 text-gray-400 hover:text-indigo-600 disabled:opacity-30 transition-colors"
                    title="Move down"
                  >
                    ▼
                  </button>
                  <button
                    onClick={() => remove(item.id)}
                    disabled={busy}
                    className="p-1 text-gray-400 hover:text-red-500 disabled:opacity-30 transition-colors"
                    title="Remove from timeline"
                  >
                    ✕
                  </button>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    );
  },
);

export default TimelinePanel;
