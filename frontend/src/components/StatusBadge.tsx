/**
 * StatusBadge — colored pill for asset pipeline status.
 */

const PROCESSING = new Set([
  "probing",
  "extracting_audio",
  "vad",
  "transcribing",
  "diarizing",
  "chunking",
  "embedding",
  "indexing_visuals",
]);

export function isProcessing(status: string): boolean {
  return status === "uploaded" || PROCESSING.has(status);
}

const LABELS: Record<string, string> = {
  uploaded: "queued",
  probing: "probing",
  extracting_audio: "extracting audio",
  vad: "detecting speech",
  transcribing: "transcribing",
  diarizing: "identifying speakers",
  chunking: "chunking",
  embedding: "indexing",
  indexing_visuals: "indexing visuals",
  ready: "ready",
  failed: "failed",
};

export default function StatusBadge({ status }: { status: string }) {
  const color =
    status === "ready"
      ? "bg-green-100 text-green-800"
      : status === "failed"
        ? "bg-red-100 text-red-800"
        : status === "uploaded"
          ? "bg-blue-100 text-blue-800"
          : "bg-yellow-100 text-yellow-800";
  const label = LABELS[status] ?? status;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold ${color}`}
    >
      {isProcessing(status) && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      )}
      {label}
    </span>
  );
}
