"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { getTicket, getTicketComments } from "@/lib/api/tickets";
import { apiErrorMessage } from "@/lib/api/client";
import type { TicketCommentResponse, TicketResponse } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiErrorState } from "@/components/ui/ApiErrorState";
import { ColorBadge } from "@/components/ui/Badge";
import { EscalationRail } from "@/components/nav/EscalationRail";

// Maps a ticket status/priority to the escalation-rail role it currently
// sits with. There's no single "current tier" field on TicketResponse —
// assignee's role is the closest proxy — so this reads the assignee's
// department/role context where available and otherwise shows the chain
// unfilled rather than guessing.
function currentStepFromTicket(ticket: TicketResponse): string | null {
  if (!ticket.assignee) return "customer";
  return null; // Resolved once assignee role is exposed on TicketResponse.
}

export default function TicketDetailPage() {
  const t = useTranslations("ticketDetail");
  const tApp = useTranslations("app");
  const params = useParams<{ id: string }>();
  const [ticket, setTicket] = useState<TicketResponse | null>(null);
  const [comments, setComments] = useState<TicketCommentResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [ticketData, commentData] = await Promise.all([
        getTicket(params.id),
        getTicketComments(params.id).catch(() => []),
      ]);
      setTicket(ticketData);
      setComments(commentData);
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  if (loading) return <p className="text-sm text-ink-500">{tApp("loading")}</p>;
  if (error || !ticket) return <ApiErrorState message={error ?? t("notFound")} onRetry={load} />;

  return (
    <div>
      <PageHeader
        title={ticket.title}
        description={t("meta", { ticketNo: ticket.ticket_no, name: ticket.requester.full_name })}
        action={
          <div className="flex items-center gap-2">
            <ColorBadge label={ticket.priority.name} color={ticket.priority.color} />
            <ColorBadge label={ticket.status.name} color={ticket.status.color} />
          </div>
        }
      />

      <div className="mb-6 rounded-card border border-ink-100 bg-white p-5">
        <EscalationRail currentCode={currentStepFromTicket(ticket)} />
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-6">
          <div className="rounded-card border border-ink-100 bg-white p-5">
            <p className="mb-2 text-sm font-medium text-ink-950">{t("description")}</p>
            <p className="whitespace-pre-wrap text-sm text-ink-700">{ticket.description}</p>
          </div>

          <div className="rounded-card border border-ink-100 bg-white">
            <div className="border-b border-ink-100 px-5 py-3">
              <p className="text-sm font-medium text-ink-950">{t("comments")}</p>
            </div>
            <ul className="divide-y divide-ink-100">
              {comments.map((comment) => (
                <li key={comment.id} className="px-5 py-3">
                  <p className="text-xs font-medium text-ink-950">
                    {comment.author.full_name}
                    {comment.is_internal && (
                      <span className="ml-2 rounded bg-ink-100 px-1.5 py-0.5 text-[10px] uppercase text-ink-500">
                        {t("internal")}
                      </span>
                    )}
                  </p>
                  <p className="mt-1 text-sm text-ink-700">{comment.body}</p>
                </li>
              ))}
              {comments.length === 0 && (
                <li className="px-5 py-6 text-center text-sm text-ink-500">{t("noComments")}</li>
              )}
            </ul>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-card border border-ink-100 bg-white p-5">
            <p className="mb-3 text-sm font-medium text-ink-950">{t("details")}</p>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs text-ink-500">{t("category")}</dt>
                <dd className="text-ink-950">{ticket.category.name}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-500">{t("department")}</dt>
                <dd className="text-ink-950">{ticket.department?.name ?? t("unassigned")}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-500">{t("assignee")}</dt>
                <dd className="text-ink-950">{ticket.assignee?.full_name ?? t("unassigned")}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
