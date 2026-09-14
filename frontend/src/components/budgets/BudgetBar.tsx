import { BUDGET_STATE_LABEL, money, percent } from '@/lib/format';
import type { BudgetProgress, BudgetState, Category } from '@/lib/types';
import { cn } from '@/lib/utils';

/** Each state's whole look in one place, so the four move together. */
const LOOK: Record<BudgetState, { bar: string; track: string; label: string }> = {
  on_pace: { bar: 'bg-income', track: '', label: 'text-income' },
  ahead_of_pace: { bar: 'bg-link', track: '', label: 'text-ink-mute' },
  warning: { bar: 'bg-warn', track: '', label: 'text-warn' },
  over: { bar: '', track: 'shame', label: 'text-shame' },
};

/**
 * A Budget's progress, loud when it breaks.
 *
 * The bar is never capped: past 100% the overrun keeps going in `shame`, which
 * is the whole point — the user is shamed, never blocked.
 */
export default function BudgetBar({
  budget,
  category,
}: {
  budget: BudgetProgress;
  category?: Category;
}) {
  const used = Number(budget.percentage);
  const over = budget.state === 'over';
  const look = LOOK[budget.state];
  const paceShare = budget.pace
    ? (Number(budget.pace) / Number(budget.amount)) * 100
    : null;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="leader">
        <span className="text-sm font-medium" style={{ color: category?.color }}>
          {category?.name ?? 'Sin categoría'}
        </span>
        <span className="dots" />
        <span className="num text-sm">
          {money(budget.spent, budget.currency)}
          <span className="text-ink-faint"> / {money(budget.amount, budget.currency)}</span>
        </span>
      </div>

      <div className={cn('bar-track', look.track)}>
        <div
          className={cn('bar', look.bar)}
          style={{ width: `${Math.min(Math.max(used, 0), 100)}%` }}
        />
        {paceShare !== null ? (
          <span
            className="marker"
            title="Ritmo esperado para hoy"
            style={{ left: `${Math.min(paceShare, 100)}%` }}
          />
        ) : null}
      </div>

      <div className="flex items-baseline justify-between">
        <span className={cn('tag', look.label)}>
          {BUDGET_STATE_LABEL[budget.state]}
        </span>
        <span className={cn('num text-xs text-ink-mute', over && 'text-shame')}>
          {percent(budget.percentage)}
          {budget.pace ? ` · ritmo ${money(budget.pace, budget.currency)}` : ''}
        </span>
      </div>
    </div>
  );
}
