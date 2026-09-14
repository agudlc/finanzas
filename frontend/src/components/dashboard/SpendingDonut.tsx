import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';

import MonthPicker from '@/components/MonthPicker';
import { Empty } from '@/components/ui/field';
import { money, percent } from '@/lib/format';
import { useSpending } from '@/lib/queries';
import type { Currency } from '@/lib/types';

/**
 * Where the month's money went.
 *
 * It carries its own month selector, so looking back a few months never moves
 * the rest of the dashboard.
 */
export default function SpendingDonut({
  month,
  onMonthChange,
  currency,
}: {
  month: string;
  onMonthChange: (month: string) => void;
  currency: Currency;
}) {
  const spending = useSpending(month);
  const slices = (spending.data?.categories ?? []).filter(
    (slice) => Number(slice.total) > 0,
  );
  const total = slices.reduce((sum, slice) => sum + Number(slice.total), 0);

  return (
    <section className="flex w-full flex-col gap-4 rounded-xl bg-paper-2 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="label">Gastos por categoría</h2>
        <MonthPicker month={month} onChange={onMonthChange} />
      </header>

      {slices.length === 0 ? (
        <Empty>No hay gastos registrados en este mes.</Empty>
      ) : (
        <div className="flex flex-col items-center gap-8 md:flex-row">
          <div className="relative h-56 w-56 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={slices}
                  dataKey={(slice) => Number(slice.total)}
                  nameKey="name"
                  innerRadius="66%"
                  outerRadius="100%"
                  paddingAngle={1}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {slices.map((slice) => (
                    <Cell key={slice.category_id} fill={slice.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="label">total</span>
              <span className="num text-sm">{money(total, currency)}</span>
            </div>
          </div>

          <ul className="flex w-full flex-col gap-2">
            {slices.map((slice) => (
              <li key={slice.category_id} className="leader">
                <span
                  className="size-2.5 shrink-0 rounded-xs"
                  style={{ background: slice.color }}
                />
                <span className="text-sm">{slice.name}</span>
                <span className="dots" />
                <span className="num text-sm">{money(slice.total, currency)}</span>
                <span className="num w-12 text-right text-xs text-ink-faint">
                  {percent((Number(slice.total) / total) * 100)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
