"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useAuth } from "@/components/auth/AuthProvider";
import { getDashboardOverview, scopeForRole } from "@/lib/api/dashboard";
import { apiErrorMessage } from "@/lib/api/client";
import type { DashboardOverviewResponse } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiErrorState } from "@/components/ui/ApiErrorState";

const WEEKS = 8;
const DAY_MS = 24 * 60 * 60 * 1000;

interface WeekBucket {
  label: string;
  total: number;
}

// Buckets the daily ticket_trend series into WEEKS rolling 7-day windows,
// oldest first, ending on today — so "last 8 weeks" always lines up with
// the current date rather than an arbitrary calendar boundary. `locale`
// drives the week-start label so month names render in the active language
// (e.g. Thai) instead of always falling back to the browser default.
function bucketByWeek(trend: DashboardOverviewResponse["ticket_trend"], locale: string): WeekBucket[] {
  const byDate = new Map<string, number>();
  for (const point of trend) byDate.set(point.date, point.value);

  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);

  const buckets: WeekBucket[] = [];
  for (let w = WEEKS - 1; w >= 0; w--) {
    const weekEnd = new Date(today.getTime() - w * 7 * DAY_MS);
    const weekStart = new Date(weekEnd.getTime() - 6 * DAY_MS);
    let total = 0;
    for (let d = 0; d < 7; d++) {
      const day = new Date(weekStart.getTime() + d * DAY_MS).toISOString().slice(0, 10);
      total += byDate.get(day) ?? 0;
    }
    buckets.push({
      label: weekStart.toLocaleDateString(locale, { month: "short", day: "numeric" }),
      total,
    });
  }
  return buckets;
}

function slaPercent(slaSummary: Record<string, number>): number | null {
  const upper = Object.fromEntries(Object.entries(slaSummary).map(([k, v]) => [k.toUpperCase(), v]));
  const met = upper.MET ?? 0;
  const breached = upper.BREACHED ?? 0;
  const decided = met + breached;
  if (decided === 0) return null;
  return (met / decided) * 100;
}

// KPI labels are localized by the caller (which has access to the
// "dashboard" translations) — this just classifies the rate into a tone + key.
type KpiKey = "noData" | "onTrack" | "atRisk" | "offTrack";

function kpiStatus(breachedTickets: number, totalTickets: number): { key: KpiKey; tone: string } {
  if (totalTickets === 0) return { key: "noData", tone: "text-ink-500" };
  const breachRate = breachedTickets / totalTickets;
  if (breachRate <= 0.05) return { key: "onTrack", tone: "text-ink-950" };
  if (breachRate <= 0.15) return { key: "atRisk", tone: "text-amber-600" };
  return { key: "offTrack", tone: "text-red-600" };
}

const ICON_CIRCLE = "flex h-12 w-12 items-center justify-center rounded-full text-white";

function TicketIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <path
        d="M3 8.5a1.5 1.5 0 0 1 0-3V4a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v1.5a1.5 1.5 0 0 1 0 3v3a1.5 1.5 0 0 1 0 3V16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-1.5a1.5 1.5 0 0 1 0-3v-3Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M13 4.5v11" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.2 2.2" strokeLinecap="round" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PieIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <path
        d="M12 3.5A8.5 8.5 0 1 0 20.5 12H12V3.5Z"
        fill="currentColor"
        fillOpacity="0.35"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M13.5 3.6A8.5 8.5 0 0 1 20.4 10.5H13.5V3.6Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function TrendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <path d="M4 16.5 9.5 11l3.5 3 6.5-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16.5 6.5H20V10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StatCard({
  icon,
  iconBg,
  value,
  valueClassName,
  label,
}: {
  icon: React.ReactNode;
  iconBg: string;
  value: string;
  valueClassName?: string;
  label: string;
}) {
  return (
    <div className="rounded-card border border-ink-100 bg-white p-5">
      <div className={`${ICON_CIRCLE} ${iconBg}`}>{icon}</div>
      <p className={`mt-4 text-3xl font-bold tracking-tight text-ink-950 ${valueClassName ?? ""}`}>{value}</p>
      <p className="mt-1 text-sm text-ink-500">{label}</p>
    </div>
  );
}

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const tApp = useTranslations("app");
  const locale = useLocale();
  const { roleCode } = useAuth();
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setOverview(await getDashboardOverview(scopeForRole(roleCode)));
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleCode]);

  const weeks = useMemo(() => (overview ? bucketByWeek(overview.ticket_trend, locale) : []), [overview, locale]);
  const maxWeekly = Math.max(1, ...weeks.map((w) => w.total));

  const sla = overview ? slaPercent(overview.sla_summary) : null;
  const kpi = overview ? kpiStatus(overview.summary.sla_breached_tickets, overview.summary.total_tickets) : null;

  const trendPercent = useMemo(() => {
    if (weeks.length < 2) return null;
    const current = weeks[weeks.length - 1].total;
    const previous = weeks[weeks.length - 2].total;
    if (previous === 0) return null;
    return ((current - previous) / previous) * 100;
  }, [weeks]);

  return (
    <div>
      <PageHeader title={t("title")} description={t("description")} />

      {loading && <p className="px-1 py-8 text-center text-sm text-ink-500">{tApp("loading")}</p>}

      {error && !loading && (
        <div className="mb-6">
          <ApiErrorState message={error} onRetry={load} />
        </div>
      )}

      {overview && !loading && !error && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={<TicketIcon />}
              iconBg="bg-teal-600"
              value={overview.summary.open_tickets.toLocaleString()}
              label={t("openTickets")}
            />
            <StatCard
              icon={<ClockIcon />}
              iconBg="bg-cyan-800"
              value={sla === null ? "—" : `${Math.round(sla)}%`}
              label={t("sla")}
            />
            <StatCard
              icon={<PieIcon />}
              iconBg="bg-sky-700"
              value={kpi ? t(kpi.key) : "—"}
              valueClassName={kpi?.tone}
              label={t("kpi")}
            />
            <StatCard
              icon={<TrendIcon />}
              iconBg="bg-teal-500"
              value={
                trendPercent === null
                  ? "—"
                  : `${trendPercent <= 0 ? "↓" : "↑"} ${Math.abs(Math.round(trendPercent))}%`
              }
              label={t("trend")}
            />
          </div>

          <div className="mt-6 rounded-card border border-ink-100 bg-white p-6">
            <h2 className="text-sm font-semibold text-ink-950">{t("ticketVolume", { weeks: WEEKS })}</h2>
            <div className="mt-8 flex items-end gap-4" style={{ height: 180 }}>
              {weeks.map((week, i) => {
                const isLast = i === weeks.length - 1;
                const height = Math.max(6, (week.total / maxWeekly) * 160);
                return (
                  <div key={week.label} className="flex flex-1 flex-col items-center gap-2">
                    <div
                      className={`w-full rounded-md ${isLast ? "bg-teal-600" : "bg-teal-100"}`}
                      style={{ height }}
                      title={t("tooltipTickets", { label: week.label, count: week.total })}
                    />
                    <span className="text-xs text-ink-500">{week.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
