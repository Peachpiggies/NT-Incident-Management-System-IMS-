"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";

export default function RootPage() {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "authed") router.replace("/dashboard");
    if (status === "guest") router.replace("/login");
  }, [status, router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-ink-50">
      <p className="text-sm text-ink-500">Loading…</p>
    </main>
  );
}
