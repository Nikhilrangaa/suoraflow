/**
 * WaveformCanvas — renders precomputed peak data on a canvas with a live
 * playhead and click-to-seek. Peaks come from the backend (computed from the
 * extracted 16 kHz mono WAV), so no raw audio is downloaded here.
 */
import { useCallback, useEffect, useRef } from "react";

interface WaveformCanvasProps {
  peaks: number[];
  duration: number;
  currentTime: number;
  onSeek: (time: number) => void;
}

const BAR_COLOR = "#c7d2fe"; // indigo-200
const PLAYED_COLOR = "#6366f1"; // indigo-500
const PLAYHEAD_COLOR = "#4338ca"; // indigo-700

export default function WaveformCanvas({
  peaks,
  duration,
  currentTime,
  onSeek,
}: WaveformCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || peaks.length === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const width = container.clientWidth;
    const height = 96;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const mid = height / 2;
    const progress = duration > 0 ? currentTime / duration : 0;
    const playedX = progress * width;

    // One vertical bar per pixel column, sampling the peak array
    for (let x = 0; x < width; x++) {
      const idx = Math.min(peaks.length - 1, Math.floor((x / width) * peaks.length));
      const amp = Math.max(0.015, peaks[idx]); // floor so silence is still visible
      const h = amp * (height * 0.9);
      ctx.fillStyle = x <= playedX ? PLAYED_COLOR : BAR_COLOR;
      ctx.fillRect(x, mid - h / 2, 1, h);
    }

    // Playhead line
    ctx.fillStyle = PLAYHEAD_COLOR;
    ctx.fillRect(playedX - 0.5, 0, 1.5, height);
  }, [peaks, duration, currentTime]);

  useEffect(() => {
    draw();
  }, [draw]);

  useEffect(() => {
    const onResize = () => draw();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [draw]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (!container || duration <= 0) return;
    const rect = container.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    onSeek(frac * duration);
  };

  return (
    <div
      ref={containerRef}
      onClick={handleClick}
      className="w-full cursor-pointer select-none"
      title="Click to seek"
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
