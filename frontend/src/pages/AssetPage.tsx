/**
 * AssetPage — media player, audio metadata, waveform, and clickable transcript.
 *
 * Polls status while the pipeline runs; when the asset becomes ready it loads
 * the transcript and waveform. Clicking the waveform or a transcript segment
 * seeks the player; the active segment highlights during playback.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, Asset, Transcript, Waveform } from "../lib/api";
import StatusBadge, { isProcessing } from "../components/StatusBadge";
import WaveformCanvas from "../components/WaveformCanvas";

interface AssetPageProps {
  assetId: string;
  initialTime?: number;
  onBack: () => void;
}

const POLL_MS = 2000;

function formatTime(sec: number): string {
  if (!isFinite(sec) || sec < 0) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function MetaItem({ label, value }: { label: string; value: string | null }) {
  if (value === null) return null;
  return (
    <div>
      <dt className="text-xs text-gray-400 uppercase tracking-wide">{label}</dt>
      <dd className="text-sm font-medium text-gray-800">{value}</dd>
    </div>
  );
}

export default function AssetPage({ assetId, initialTime, onBack }: AssetPageProps) {
  const [asset, setAsset] = useState<Asset | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [waveform, setWaveform] = useState<Waveform | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  const mediaRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null);
  const activeSegRef = useRef<HTMLButtonElement | null>(null);
  const appliedInitialTime = useRef(false);

  const loadDetails = useCallback((a: Asset) => {
    if (a.status !== "ready") return;
    api.assets
      .transcript(a.id)
      .then(setTranscript)
      .catch(() => setTranscript(null));
    if (a.media_type === "video" || a.media_type === "audio") {
      api.assets
        .waveform(a.id)
        .then(setWaveform)
        .catch(() => setWaveform(null)); // e.g. no-audio b-roll
    }
  }, []);

  // Initial load
  useEffect(() => {
    api.assets
      .get(assetId)
      .then((a) => {
        setAsset(a);
        loadDetails(a);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load asset"),
      );
  }, [assetId, loadDetails]);

  // Live status polling while the pipeline runs
  useEffect(() => {
    if (!asset || !isProcessing(asset.status)) return;
    const timer = setInterval(() => {
      api.assets
        .get(assetId)
        .then((a) => {
          setAsset(a);
          if (!isProcessing(a.status)) loadDetails(a);
        })
        .catch(() => {
          /* transient poll errors are ignored */
        });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [asset, assetId, loadDetails]);

  const seek = useCallback((time: number) => {
    const el = mediaRef.current;
    if (!el) return;
    el.currentTime = time;
    setCurrentTime(time);
    void el.play().catch(() => {
      /* autoplay may be blocked; the user can press play */
    });
  }, []);

  // Apply ?t= deep-link once media is ready
  const handleLoadedMetadata = () => {
    if (initialTime && !appliedInitialTime.current && mediaRef.current) {
      appliedInitialTime.current = true;
      mediaRef.current.currentTime = initialTime;
      setCurrentTime(initialTime);
    }
  };

  // Keep the active transcript segment scrolled into view
  const activeSegId = transcript?.segments.find(
    (s) => currentTime >= s.start && currentTime < s.end,
  )?.id;

  useEffect(() => {
    activeSegRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeSegId]);

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error}</p>
          <button onClick={onBack} className="text-indigo-600 hover:underline text-sm">
            Back
          </button>
        </div>
      </div>
    );
  }

  if (!asset) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 animate-pulse">Loading asset...</p>
      </div>
    );
  }

  const processing = isProcessing(asset.status);
  const mediaUrl = api.assets.mediaUrl(asset.id);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
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
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-gray-900 truncate">
              {asset.original_filename}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <StatusBadge status={asset.status} />
              <span className="text-xs text-gray-400 uppercase">{asset.media_type}</span>
              <span className="text-xs text-gray-400">{formatBytes(asset.size_bytes)}</span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6 space-y-6">
        {asset.status === "failed" && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            {asset.error_message ?? "Processing failed."}
          </div>
        )}

        {processing && (
          <div className="rounded-lg bg-yellow-50 border border-yellow-200 p-4 text-sm text-yellow-800 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
            Processing in progress — this page updates automatically.
          </div>
        )}

        {/* Player */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          {asset.media_type === "video" ? (
            <video
              ref={(el) => {
                mediaRef.current = el;
              }}
              src={mediaUrl}
              controls
              preload="metadata"
              onLoadedMetadata={handleLoadedMetadata}
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              className="w-full max-h-[420px] rounded-lg bg-black"
            />
          ) : (
            <audio
              ref={(el) => {
                mediaRef.current = el;
              }}
              src={mediaUrl}
              controls
              preload="metadata"
              onLoadedMetadata={handleLoadedMetadata}
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              className="w-full"
            />
          )}

          {/* Waveform */}
          {waveform && waveform.peaks.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                <span>{formatTime(currentTime)}</span>
                <span>{formatTime(waveform.duration)}</span>
              </div>
              <WaveformCanvas
                peaks={waveform.peaks}
                duration={waveform.duration}
                currentTime={currentTime}
                onSeek={seek}
              />
            </div>
          )}
        </div>

        {/* Audio-first metadata */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Media Info</h2>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <MetaItem
              label="Sample Rate"
              value={asset.sample_rate ? `${asset.sample_rate.toLocaleString()} Hz` : null}
            />
            <MetaItem
              label="Channels"
              value={
                asset.channels !== null
                  ? asset.channels === 1
                    ? "1 (mono)"
                    : asset.channels === 2
                      ? "2 (stereo)"
                      : String(asset.channels)
                  : null
              }
            />
            <MetaItem label="Audio Codec" value={asset.audio_codec} />
            <MetaItem
              label="Duration"
              value={asset.duration !== null ? formatTime(asset.duration) : null}
            />
            <MetaItem
              label="Resolution"
              value={asset.width && asset.height ? `${asset.width}×${asset.height}` : null}
            />
            <MetaItem
              label="Frame Rate"
              value={asset.fps !== null ? `${asset.fps} fps` : null}
            />
            <MetaItem
              label="Speech"
              value={
                asset.speech_ratio !== null
                  ? `${Math.round(asset.speech_ratio * 100)}%`
                  : null
              }
            />
            <MetaItem
              label="Speech Regions"
              value={
                asset.vad_segment_count !== null ? String(asset.vad_segment_count) : null
              }
            />
          </dl>
        </div>

        {/* Transcript */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Transcript</h2>
          {asset.status !== "ready" ? (
            <p className="text-sm text-gray-400">
              {processing
                ? "The transcript will appear when processing finishes."
                : "No transcript available."}
            </p>
          ) : !transcript || transcript.segments.length === 0 ? (
            <p className="text-sm text-gray-400">
              No speech was detected in this file.
            </p>
          ) : (
            <div className="space-y-1 max-h-[480px] overflow-y-auto pr-1">
              {transcript.segments.map((seg) => {
                const active = seg.id === activeSegId;
                return (
                  <button
                    key={seg.id}
                    ref={active ? activeSegRef : null}
                    onClick={() => seek(seg.start)}
                    className={`w-full text-left rounded-lg px-3 py-2 transition-colors ${
                      active
                        ? "bg-indigo-50 border border-indigo-200"
                        : "hover:bg-gray-50 border border-transparent"
                    }`}
                  >
                    <span className="flex items-baseline gap-3">
                      <span className="text-xs font-mono text-indigo-600 shrink-0 w-12">
                        {formatTime(seg.start)}
                      </span>
                      <span className="text-xs text-gray-400 shrink-0 w-20 truncate">
                        {seg.speaker}
                      </span>
                      <span className="text-sm text-gray-800">{seg.text}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
