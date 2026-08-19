export function ApiErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-card border border-ink-100 bg-white p-8 text-center">
      <p className="text-sm font-medium text-ink-950">Couldn&apos;t load this</p>
      <p className="mt-1 text-sm text-ink-500">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-md bg-ink-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-ink-800"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-card border border-dashed border-ink-100 bg-white p-10 text-center">
      <p className="text-sm font-medium text-ink-950">{title}</p>
      {description && <p className="mt-1 text-sm text-ink-500">{description}</p>}
    </div>
  );
}
