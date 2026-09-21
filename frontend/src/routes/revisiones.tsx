import { useState } from 'react';
import { createFileRoute, Link } from '@tanstack/react-router';
import { ArrowLeft } from 'lucide-react';

import ReviewRow from '@/components/reviews/ReviewRow';
import { Empty, ErrorText, PageTitle } from '@/components/ui/field';
import { useReviews } from '@/lib/queries';

export const Route = createFileRoute('/revisiones')({
  component: Revisiones,
});

/**
 * The Reviews history: every run the app has made, newest first.
 *
 * A Review happens in the worker and the Inbox only ever shows what came out
 * of it, so this is where a run is answerable: what triggered it, whether it
 * called the model, what it cost, what it left behind and — opened — the whole
 * conversation it was. One run at a time is open, because the question is
 * always about one of them.
 */
function Revisiones() {
  const reviews = useReviews();
  const [open, setOpen] = useState<string | null>(null);
  const runs = reviews.data ?? [];

  return (
    <div className="flex w-full max-w-3xl flex-col gap-10">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <PageTitle>Revisiones</PageTitle>
        <Link
          to="/bandeja"
          className="flex items-center gap-1.5 text-sm text-ink-mute hover:text-ink"
        >
          <ArrowLeft size={14} /> Bandeja
        </Link>
      </header>

      <ErrorText error={reviews.error} />

      <div className="flex flex-col gap-3">
        {runs.map((review) => (
          <ReviewRow
            key={review.id}
            review={review}
            open={open === review.id}
            onToggle={() => setOpen(open === review.id ? null : review.id)}
          />
        ))}
      </div>

      {!reviews.isPending && runs.length === 0 && (
        <Empty>Todavía no corrió ninguna revisión.</Empty>
      )}
    </div>
  );
}
