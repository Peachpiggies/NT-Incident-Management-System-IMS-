'use client';

import { useEffect, useState } from "react";

type BackendHealth =
  | { state: "loading" }
  | { state: "ready"; database: string }
  | { state: "error"; message: string };

export default function Home() {
  const [health, setHealth] = useState<BackendHealth>({ state: "loading" });
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  useEffect(() => {
    if (!apiUrl) {
      setHealth({ state: "error", message: "Backend URL is not configured" });
      return;
    }

    const controller = new AbortController();
    setHealth({ state: "loading" });

    async function checkBackend() {
      try {
        const response = await fetch(`${apiUrl}/readyz`, {
          cache: "no-store",
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Readiness check returned ${response.status}`);
        }

        const data: { status?: string; database?: string } = await response.json();
        if (data.status !== "ok" || data.database !== "connected") {
          throw new Error("Database is not ready");
        }

        setHealth({ state: "ready", database: data.database });
      } catch (error) {
        if (!controller.signal.aborted) {
          setHealth({
            state: "error",
            message: error instanceof Error ? error.message : "Backend is unreachable",
          });
        }
      }
    }

    void checkBackend();
    return () => controller.abort();
  }, [apiUrl]);

  return (
    <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
      <h1>Incident Management Platform (IMP)</h1>
      <p aria-live="polite">
        Backend status: {health.state === "loading" && "Checking database readiness…"}
        {health.state === "ready" && `Ready (${health.database})`}
        {health.state === "error" && `Unavailable — ${health.message}`}
      </p>
      <p>
        {apiUrl ? (
          <span>Backend requests will be sent to {apiUrl}</span>
        ) : (
          <span>
            Backend not configured. Add <code>NEXT_PUBLIC_API_URL</code> to your
            frontend environment and start the backend.
          </span>
        )}
      </p>
    </main>
  );
}
