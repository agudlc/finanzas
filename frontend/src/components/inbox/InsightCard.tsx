import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ErrorText } from '@/components/ui/field';
import { useDismissInsight } from '@/lib/queries';
import type { Insight } from '@/lib/types';

/**
 * One observation, said and left there.
 *
 * It changes nothing, so the card has no yes and no no: the only answer to an
 * observation is having read it. Dismissing takes it out of the Inbox and
 * keeps it as history — the agent reads back what it already said so it does
 * not say it twice.
 */
export default function InsightCard({ insight }: { insight: Insight }) {
  const dismissal = useDismissInsight();

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-dashed border-rule p-5">
      <header className="leader">
        <span className="text-sm">{insight.topic}</span>
        <Badge variant="outline">observación</Badge>
      </header>

      <p className="text-sm text-ink-mute">{insight.body}</p>

      <ErrorText error={dismissal.error} />

      <div className="flex justify-end">
        <Button
          variant="ghost"
          size="sm"
          disabled={dismissal.isPending}
          onClick={() => dismissal.mutate(insight.id)}
        >
          {dismissal.isPending ? 'Guardando…' : 'Leído'}
        </Button>
      </div>
    </article>
  );
}
