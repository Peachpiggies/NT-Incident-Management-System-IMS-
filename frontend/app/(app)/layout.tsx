"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { Sidebar } from "@/components/nav/Sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "guest") router.replace("/login");
  }, [status, router]);

  if (status !== "authed") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink-50">
        <p className="text-sm text-ink-500">Loading…</p>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen bg-ink-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto px-8 py-8">{children}</main>
    </div>
  );
}
