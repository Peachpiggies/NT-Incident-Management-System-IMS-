'use client';

import React, { useEffect, useState } from "react";

export default function Home() {
  const [status, setStatus] = useState<string>("loading");
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  useEffect(() => {
    if (!apiUrl) {
      setStatus("backend URL not configured");
      return;
    }

    fetch(`${apiUrl}/healthz`)
      .then((r) => r.json())
      .then((data) => setStatus(data.status ?? "unknown"))
      .catch(() => setStatus("unreachable"));
  }, [apiUrl]);

  return (
    <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
      <h1>Incident Management Platform (IMP)</h1>
      <p>Backend status: {status}</p>
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