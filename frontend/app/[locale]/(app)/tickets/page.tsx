"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { listTickets } from "@/lib/api/tickets";
import { listPriorities, listStatuses } from "@/lib/api/references";
import { apiErrorMessage } from "@/lib/api/client";
import type { PriorityResponse, StatusResponse, TicketPage } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiErrorState } from "@/components/ui/ApiErrorState";
import { ColorBadge } from "@/components/ui/Badge";

export default function TicketsPage() {
  const t = useTranslations("tickets");
  const tApp = useTranslations("app");
  const [page, setPage] = useState<TicketPage | null>(null);
  const [statuses, setStatuses] = useState<StatusResponse[]>([]);
  const [priorities, setPriorities] = useState<PriorityResponse[]>([]);
  const [statusId, setStatusId] = useState("");
  const [priorityId, setPriorityId] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listTickets({
        q: q || undefined,
        status_id: statusId || undefined,
        priority_id: priorityId || undefined,
        limit: 50,
        sort_by: "created_at",
        sort_order: "desc",
      });
      setPage(data);
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // GET /priorities and /statuses back these filter dropdowns.
    void listPriorities().then(setPriorities).catch(() => setPriorities([]));
    void listStatuses().then(setStatuses).catch(() => setStatuses([]));
  }, []);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusId, priorityId]);

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("description")}
        action={
          <Link
            href="/tickets/new"
            className="rounded-md bg-accent-600 px-3 py-2 text-sm font-medium text-white hover:bg-accent-500"
          >
            {t("newTicket")}
          </Link>
        }
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
        className="mb-4 flex flex-wrap items-center gap-3"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("searchPlaceholder")}
          className="w-64 rounded-md border border-ink-100 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
        />
        <select
          value={statusId}
          onChange={(e) => setStatusId(e.target.value)}
          className="rounded-md border border-ink-100 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
        >
          <option value="">{t("allStatuses")}</option>
          {statuses.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <select
          value={priorityId}
          onChange={(e) => setPriorityId(e.target.value)}
          className="rounded-md border border-ink-100 bg-white px-3 py-2 text-sm outline-none focus:border-accent-500"
        >
          <option value="">{t("allPriorities")}</option>
          {priorities.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded-md border border-ink-100 bg-white px-3 py-2 text-sm font-medium text-ink-700 hover:border-ink-300"
        >
          {t("search")}
        </button>
      </form>

      <div className="overflow-hidden rounded-card border border-ink-100 bg-white">
        {loading && <p className="px-5 py-8 text-center text-sm text-ink-500">{tApp("loading")}</p>}
        {error && (
          <div className="p-5">
            <ApiErrorState message={error} onRetry={load} />
          </div>
        )}

        {!loading && !error && page && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-ink-100 bg-ink-50 text-xs font-medium uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-5 py-3">{t("colTicket")}</th>
                <th className="px-5 py-3">{t("colRequester")}</th>
                <th className="px-5 py-3">{t("colAssignee")}</th>
                <th className="px-5 py-3">{t("colPriority")}</th>
                <th className="px-5 py-3">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {page.items.map((ticket) => (
                <tr key={ticket.id} className="hover:bg-ink-50">
                  <td className="px-5 py-3">
                    <Link href={`/tickets/${ticket.id}`} className="font-medium text-ink-950 hover:text-accent-600">
                      {ticket.title}
                    </Link>
                    <p className="text-xs text-ink-500">{ticket.ticket_no}</p>
                  </td>
                  <td className="px-5 py-3 text-ink-700">{ticket.requester.full_name}</td>
                  <td className="px-5 py-3 text-ink-700">{ticket.assignee?.full_name ?? t("unassigned")}</td>
                  <td className="px-5 py-3">
                    <ColorBadge label={ticket.priority.name} color={ticket.priority.color} />
                  </td>
                  <td className="px-5 py-3">
                    <ColorBadge label={ticket.status.name} color={ticket.status.color} />
                  </td>
                </tr>
              ))}
              {page.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-sm text-ink-500">
                    {t("noResults")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
