import { ChevronDown, ChevronRight } from 'lucide-react';

import Transcript from '@/components/reviews/Transcript';
import { Badge } from '@/components/ui/badge';
import { ErrorText } from '@/components/ui/field';
import {
  REVIEW_NOTE_LABEL,
  REVIEW_STATUS_LABEL,
  REVIEW_TRIGGER_LABEL,
  SUGGESTION_KIND_LABEL,
  SUGGESTION_STATUS_LABEL,
  monthName,
  quantity,
  timestamp,
} from '@/lib/format';
import { useReview } from '@/lib/queries';
import type { ProducedSuggestion, ReviewDetail, ReviewSummary } from '@/lib/types';

/**
 * One run in the history: how it went, and, once opened, what it was.
 *
 * The line alone answers the everyday question — did it run, did it call the
 * model, what did it cost, did anything go wrong — and the detail is only
 * fetched when the user asks for it, because a transcript is far bigger than
 * everything else on the screen put together.
 */
export default function ReviewRow({
  review,
  open,
  onToggle,
}: {
  review: ReviewSummary;
  open: boolean;
  onToggle: () => void;
}) {
  // Only opening a run fetches it: the transcript is bigger than the whole
  // list around it.
  const detail = useReview(open ? review.id : null);

  return (
    <article className="rounded-xl border border-rule">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full flex-col gap-2 p-5 text-left"
      >
        <header className="leader">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="text-sm">{REVIEW_TRIGGER_LABEL[review.trigger]}</span>
          {review.used_agent && <Badge variant="outline">agente</Badge>}
          <Badge variant={review.status === 'failed' ? 'destructive' : 'secondary'}>
            {REVIEW_STATUS_LABEL[review.status]}
          </Badge>
          <span className="dots" />
          <span className="num text-sm">{timestamp(review.created_at)}</span>
        </header>

        <p className="tag">
          {monthName(review.month)}
          {cost(review) && <> · {cost(review)}</>}
          {review.note && <> · {REVIEW_NOTE_LABEL[review.note] ?? review.note}</>}
        </p>

        {review.error && (
          <p className="flex flex-col gap-0.5 text-sm text-shame">
            No pudo terminar.
            {/* What broke is the API's own words, kept as they came for the
                same reason the transcript is: this is the line someone would
                paste when asking why. */}
            <span className="num text-xs">{review.error}</span>
          </p>
        )}
      </button>

      {open && (
        <div className="flex flex-col gap-6 border-t border-rule-soft p-5">
          <ErrorText error={detail.error} />
          {detail.isPending && <p className="tag">Buscando la revisión…</p>}
          {detail.data && <Detail review={detail.data} />}
        </div>
      )}
    </article>
  );
}

/** What the run cost, when it called anybody: the two counts move together. */
function cost(review: ReviewSummary): string | null {
  if (review.input_tokens === null || review.output_tokens === null) return null;
  return `${quantity(review.input_tokens)} tokens de entrada, ${quantity(
    review.output_tokens,
  )} de salida`;
}

function Detail({ review }: { review: ReviewDetail }) {
  const nothing =
    review.suggestions.length === 0 && review.insights.length === 0;

  return (
    <>
      <section className="flex flex-col gap-3">
        <h3 className="label">Lo que dejó</h3>
        {nothing && (
          <p className="text-sm text-ink-mute">
            No propuso ni observó nada en esta revisión.
          </p>
        )}
        {review.suggestions.map((suggestion) => (
          <Proposed key={suggestion.id} suggestion={suggestion} />
        ))}
        {review.insights.map((insight) => (
          <div key={insight.id} className="flex flex-col gap-1">
            <header className="leader">
              <span className="text-sm">{insight.topic}</span>
              <Badge variant="outline">observación</Badge>
            </header>
            <p className="text-sm text-ink-mute">{insight.body}</p>
          </div>
        ))}
      </section>

      {review.transcript && (
        <section className="flex flex-col gap-3">
          <header className="leader">
            <h3 className="label">La conversación</h3>
            <span className="dots" />
            <span className="tag">prompt {review.prompt_version}</span>
          </header>
          <Transcript turns={review.transcript} />
        </section>
      )}
    </>
  );
}

function Proposed({ suggestion }: { suggestion: ProducedSuggestion }) {
  return (
    <div className="flex flex-col gap-1">
      <header className="leader">
        <span className="text-sm">{SUGGESTION_KIND_LABEL[suggestion.kind]}</span>
        <Badge variant="outline">
          {SUGGESTION_STATUS_LABEL[suggestion.status]}
        </Badge>
      </header>
      <p className="text-sm text-ink-mute">{suggestion.rationale}</p>
      {suggestion.rejection_reason && (
        <p className="tag">Dijiste que no: {suggestion.rejection_reason}</p>
      )}
    </div>
  );
}
