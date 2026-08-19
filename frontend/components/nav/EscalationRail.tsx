"use client";

import { useTranslations } from "next-intl";

/**
 * Shows where a ticket sits in the ownership chain. Rebuilt against the
 * real seeded roles (customer / helpdesk_t1 / helpdesk_t2 / manager / admin)
 * — there is no Tier 3; that was specific to the marketing deck, not this
 * backend. `admin` is an operator role, not a workflow tier, so it isn't
 * shown as a rail step.
 *
 * Labels are sourced from the shared "role" translation namespace so this
 * rail and RoleBadge never drift out of sync across locales.
 */
const CHAIN_CODES = ["customer", "helpdesk_t1", "helpdesk_t2", "manager"] as const;

export function EscalationRail({ currentCode }: { currentCode: string | null }) {
  const t = useTranslations("role");
  const currentIndex = CHAIN_CODES.findIndex((code) => code === currentCode);

  return (
    <div className="flex items-center gap-2">
      {CHAIN_CODES.map((code, index) => {
        const isActive = index === currentIndex;
        const isPast = currentIndex >= 0 && index < currentIndex;
        return (
          <div key={code} className="flex items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                isActive
                  ? "bg-accent-600 text-white"
                  : isPast
                  ? "bg-ink-100 text-ink-500"
                  : "bg-ink-50 text-ink-300"
              }`}
            >
              {t(code)}
            </span>
            {index < CHAIN_CODES.length - 1 && <span className="text-ink-300">→</span>}
          </div>
        );
      })}
    </div>
  );
}
