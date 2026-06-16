/**
 * App.tsx — Root component with minimal state-based router.
 * Dashboard is the main view; clicking a project navigates to ProjectPage.
 * A small health indicator is shown in the bottom-right corner.
 */
import { useEffect, useState } from "react";
import { api } from "./lib/api";
import Dashboard from "./pages/Dashboard";
import ProjectPage from "./pages/ProjectPage";

type Route =
  | { page: "dashboard" }
  | { page: "project"; id: string };

function HealthIndicator() {
  const [status, setStatus] = useState<"loading" | "ok" | "degraded">("loading");

  useEffect(() => {
    api
      .health()
      .then((data) => setStatus(data.status === "ok" ? "ok" : "degraded"))
      .catch(() => setStatus("degraded"));
  }, []);

  const color =
    status === "ok"
      ? "bg-green-500"
      : status === "degraded"
        ? "bg-red-500"
        : "bg-gray-400";

  const label =
    status === "ok" ? "Backend ok" : status === "degraded" ? "Backend degraded" : "Checking...";

  return (
    <div
      className="fixed bottom-3 right-3 flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-3 py-1 shadow-sm text-xs text-gray-500"
      title={label}
    >
      <span className={`w-2 h-2 rounded-full ${color}`} />
      {label}
    </div>
  );
}

export default function App() {
  const [route, setRoute] = useState<Route>({ page: "dashboard" });

  const navigate = (r: Route) => setRoute(r);

  return (
    <>
      {route.page === "dashboard" && (
        <Dashboard onSelectProject={(id) => navigate({ page: "project", id })} />
      )}
      {route.page === "project" && (
        <ProjectPage
          projectId={route.id}
          onBack={() => navigate({ page: "dashboard" })}
        />
      )}
      <HealthIndicator />
    </>
  );
}
