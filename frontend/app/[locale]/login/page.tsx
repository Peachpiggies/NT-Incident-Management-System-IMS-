"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/components/auth/AuthProvider";

export default function LoginPage() {
  const t = useTranslations("login");
  const tApp = useTranslations("app");
  const { login, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(email, password);
    } catch {
      // error state surfaced via useAuth().error
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <div className="w-full max-w-sm rounded-card border border-ink-800 bg-ink-900 p-8 shadow-xl">
        <p className="text-sm font-semibold tracking-tight text-white">{tApp("name")}</p>
        <h1 className="mt-1 text-lg font-medium text-ink-100">{t("title")}</h1>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-ink-300">{t("emailLabel")}</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border border-ink-700 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-accent-500"
              placeholder="you@company.com"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-ink-300">{t("passwordLabel")}</span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border border-ink-700 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-accent-500"
              placeholder="••••••••••••"
            />
          </label>

          {error && <p className="text-xs font-medium text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="mt-2 rounded-md bg-accent-600 px-3 py-2 text-sm font-medium text-white hover:bg-accent-500 disabled:opacity-60"
          >
            {submitting ? t("submitting") : t("submit")}
          </button>
        </form>
      </div>
    </main>
  );
}
