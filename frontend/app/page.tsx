"use client";
// Ensure JSX intrinsic elements are available in environments where TSX types aren't loaded
declare global {
  namespace JSX {
    interface IntrinsicElements {
      main: any;
      h1: any;
      p: any;
      a: any;
    }
  }
}
/// <reference types="react" />
import React, { useEffect, useState } from "react";

export default function Home() {
  const [status, setStatus] = useState<string>("loading");

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/healthz`)
      .then((r) => r.json())
      .then((data) => setStatus(data.status ?? "unknown"))
      .catch(() => setStatus("unreachable"));
  }, []);

  return (
    <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
      <h1>Incident Management Platform (IMP)</h1>
      <p>Backend status: {status}</p>
      <p>
        Open <a href="/api">App routes</a>.
      </p>
    </main>
  );
}