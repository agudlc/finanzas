import { createFileRoute, Link } from '@tanstack/react-router';
import { History, RefreshCw } from 'lucide-react';

import InsightCard from '@/components/inbox/InsightCard';
import SuggestionCard from '@/components/inbox/SuggestionCard';
import { Button } from '@/components/ui/button';
import { Empty, ErrorText, PageTitle } from '@/components/ui/field';
import { monthName } from '@/lib/format';
import { useCategories, useInbox, useRunReview } from '@/lib/queries';
import type { InboxSuggestion } from '@/lib/types';

export const Route = createFileRoute('/bandeja')({
  component: Bandeja,
});

/**
 * The Inbox: what the app proposes and what it noticed, waiting for the user.
 *
 * A Review runs in the worker, so pressing "Revisar ahora" does not hand back
 * the proposals — it hands back Reviews that are queued. The screen says so and
 * polls until they finish, which is also what makes a worker that is down
 * visible instead of silent.
 *
 * Observations sit in their own section rather than among the proposals: there
 * is nothing to accept in one, and mixing them would make "Aceptar" mean two
 * different things on the same screen.
 */
function Bandeja() {
  const inbox = useInbox();
  const categories = useCategories();
  const run = useRunReview();
  const byId = new Map((categories.data ?? []).map((one) => [one.id, one]));

  const working = (inbox.data?.reviews.length ?? 0) > 0;
  const months = groupByMonth(inbox.data?.suggestions ?? []);
  const insights = inbox.data?.insights ?? [];
  const empty = months.length === 0 && insights.length === 0;

  return (
    <div className="flex w-full max-w-3xl flex-col gap-10">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <PageTitle>Bandeja</PageTitle>
        <div className="flex items-center gap-2">
          {/* Where a proposal came from: the run that made it, and what it
              was told. The Inbox itself says nothing about the runs. */}
          <Button variant="ghost" size="sm" render={<Link to="/revisiones" />}>
            <History /> Revisiones
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={run.isPending || working}
            onClick={() => run.mutate(undefined)}
          >
            <RefreshCw /> Revisar ahora
          </Button>
        </div>
      </header>

      <ErrorText error={inbox.error ?? run.error} />

      {working && (
        <p className="tag">
          Estoy mirando tus gastos recurrentes, tus presupuestos y cómo viene el
          mes…
        </p>
      )}

      {months.map(([month, suggestions]) => (
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
      ))}

      {insights.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="label">Observaciones</h2>
          {insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </section>
      )}

      {empty && (
        <Empty>
          No hay nada esperándote. Probá "Revisar ahora" si acabás de agregar un
          gasto recurrente.
        </Empty>
      )}
    </div>
  );
}

/** The months that have something pending, newest first. */
function groupByMonth(
  suggestions: InboxSuggestion[],
): [string, InboxSuggestion[]][] {
  const months = new Map<string, InboxSuggestion[]>();
  for (const suggestion of suggestions) {
    const month = suggestion.month.slice(0, 7);
    months.set(month, [...(months.get(month) ?? []), suggestion]);
  }
  return [...months].sort(([a], [b]) => b.localeCompare(a));
}
