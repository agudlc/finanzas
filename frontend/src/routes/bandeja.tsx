import { createFileRoute } from '@tanstack/react-router';
import { RefreshCw } from 'lucide-react';

import SuggestionCard from '@/components/inbox/SuggestionCard';
import { Button } from '@/components/ui/button';
import { Empty, ErrorText, PageTitle } from '@/components/ui/field';
import { monthName } from '@/lib/format';
import { useCategories, useInbox, useRunReview } from '@/lib/queries';
import type { Suggestion } from '@/lib/types';

export const Route = createFileRoute('/bandeja')({
  component: Bandeja,
});

/**
 * The Inbox: what the app proposes, waiting for the user.
 *
 * A Review runs in the worker, so pressing "Revisar ahora" does not hand back
 * the proposals — it hands back a Review that is queued. The screen says so and
 * polls until it finishes, which is also what makes a worker that is down
 * visible instead of silent.
 */
function Bandeja() {
  const inbox = useInbox();
  const categories = useCategories();
  const run = useRunReview();
  const byId = new Map((categories.data ?? []).map((one) => [one.id, one]));

  const working = (inbox.data?.reviews.length ?? 0) > 0;
  const months = groupByMonth(inbox.data?.suggestions ?? []);

  return (
    <div className="flex w-full max-w-3xl flex-col gap-10">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <PageTitle>Bandeja</PageTitle>
        <Button
          variant="outline"
          size="sm"
          disabled={run.isPending || working}
          onClick={() => run.mutate(undefined)}
        >
          <RefreshCw /> Revisar ahora
        </Button>
      </header>

      <ErrorText error={inbox.error ?? run.error} />

      {working && (
        <p className="tag">Estoy revisando tus gastos recurrentes…</p>
      )}

      {months.length > 0 ? (
        months.map(([month, suggestions]) => (
          <section key={month} className="flex flex-col gap-4">
            <h2 className="label">{monthName(month)}</h2>
            {suggestions.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                categories={categories.data ?? []}
                category={byId.get(suggestion.payload.category_id)}
              />
            ))}
          </section>
        ))
      ) : (
        <Empty>
          No hay nada esperándote. Probá "Revisar ahora" si acabás de agregar un
          gasto recurrente.
        </Empty>
      )}
    </div>
  );
}

/** The months that have something pending, newest first. */
function groupByMonth(suggestions: Suggestion[]): [string, Suggestion[]][] {
  const months = new Map<string, Suggestion[]>();
  for (const suggestion of suggestions) {
    const month = suggestion.month.slice(0, 7);
    months.set(month, [...(months.get(month) ?? []), suggestion]);
  }
  return [...months].sort(([a], [b]) => b.localeCompare(a));
}
