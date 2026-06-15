import { useEffect, useState } from "react";

interface HealthData {
  status: string;
  db: string;
  redis: string;
}

type FetchState =
  | { kind: "loading" }
  | { kind: "ok"; data: HealthData }
  | { kind: "error"; message: string };

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function StatusBadge({ value }: { value: string }) {
  const isOk = value === "ok";
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-sm font-semibold ${
        isOk
          ? "bg-green-100 text-green-800"
          : "bg-red-100 text-red-800"
      }`}
    >
      {value}
    </span>
  );
}

export default function App() {
  const [state, setState] = useState<FetchState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<HealthData>;
      })
      .then((data) => setState({ kind: "ok", data }))
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Unknown error",
        });
      });

    return () => controller.abort();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="bg-white rounded-xl shadow-md p-8 w-full max-w-sm">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">SuoraFlow</h1>
        <p className="text-sm text-gray-500 mb-6">Backend health status</p>

        {state.kind === "loading" && (
          <p className="text-gray-400 animate-pulse">Checking backend…</p>
        )}

        {state.kind === "error" && (
          <div className="rounded bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
            <strong>Could not reach backend</strong>
            <br />
            {state.message}
          </div>
        )}

        {state.kind === "ok" && (
          <table className="w-full text-sm">
            <tbody className="divide-y divide-gray-100">
              <tr className="py-2">
                <td className="py-2 pr-4 text-gray-500 font-medium">Overall</td>
                <td className="py-2">
                  <StatusBadge value={state.data.status} />
                </td>
              </tr>
              <tr>
                <td className="py-2 pr-4 text-gray-500 font-medium">Database</td>
                <td className="py-2">
                  <StatusBadge value={state.data.db} />
                </td>
              </tr>
              <tr>
                <td className="py-2 pr-4 text-gray-500 font-medium">Redis</td>
                <td className="py-2">
                  <StatusBadge value={state.data.redis} />
                </td>
              </tr>
            </tbody>
          </table>
        )}

        <p className="mt-6 text-xs text-gray-400">
          API: {API_URL}
        </p>
      </div>
    </div>
  );
}
