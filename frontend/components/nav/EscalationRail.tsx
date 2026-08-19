/**
 * Shows where a ticket sits in the ownership chain. Rebuilt against the
 * real seeded roles (customer / helpdesk_t1 / helpdesk_t2 / manager / admin)
 * — there is no Tier 3; that was specific to the marketing deck, not this
 * backend. `admin` is an operator role, not a workflow tier, so it isn't
 * shown as a rail step.
 */
const CHAIN: { code: string; label: string }[] = [
  { code: "customer", label: "Customer" },
  { code: "helpdesk_t1", label: "Helpdesk T1" },
  { code: "helpdesk_t2", label: "Helpdesk T2" },
  { code: "manager", label: "Manager" },
];

export function EscalationRail({ currentCode }: { currentCode: string | null }) {
  const currentIndex = CHAIN.findIndex((step) => step.code === currentCode);

  return (
    <div className="flex items-center gap-2">
      {CHAIN.map((step, index) => {
        const isActive = index === currentIndex;
        const isPast = currentIndex >= 0 && index < currentIndex;
        return (
          <div key={step.code} className="flex items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                isActive
                  ? "bg-accent-600 text-white"
                  : isPast
                  ? "bg-ink-100 text-ink-500"
                  : "bg-ink-50 text-ink-300"
              }`}
            >
              {step.label}
            </span>
            {index < CHAIN.length - 1 && <span className="text-ink-300">→</span>}
          </div>
        );
      })}
    </div>
  );
}
