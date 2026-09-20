import { Badge } from '@/components/ui/badge';
import { longDay, money } from '@/lib/format';
import type { Category, Suggestion } from '@/lib/types';

/**
 * One proposal, said plainly: what it would record, and why.
 *
 * The user decides from this card alone, so it never hides behind "gasto
 * recurrente de marzo" — the amount, the day and the category are all here.
 */
export default function SuggestionCard({
  suggestion,
  category,
}: {
  suggestion: Suggestion;
  category?: Category;
}) {
  const { description, amount, currency, date, is_fixed } = suggestion.payload;

  return (
    <article className="flex flex-col gap-3 rounded-xl bg-paper-2 p-5">
      <header className="leader">
        <span className="text-sm">{description}</span>
        <Badge variant="outline">nuevo gasto</Badge>
        <span className="dots" />
        <span className="num text-sm">{money(amount, currency)}</span>
      </header>

      <p className="tag">
        {longDay(date)} · {category?.name ?? 'sin categoría'}
        {is_fixed ? ' · fijo' : ''}
      </p>

      <p className="text-sm text-ink-mute">{suggestion.rationale}</p>
    </article>
  );
}
