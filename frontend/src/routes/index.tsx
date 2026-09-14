import { useState } from 'react';
import { createFileRoute, Link } from '@tanstack/react-router';

import SpendingDonut from '@/components/dashboard/SpendingDonut';
import BudgetBar from '@/components/budgets/BudgetBar';
import TransactionList from '@/components/transactions/TransactionList';
import MonthPicker from '@/components/MonthPicker';
import { Empty, ErrorText, PageTitle } from '@/components/ui/field';
import heroImage from '@/assets/hero.png';
import { heroMoney, money, monthKey, monthName } from '@/lib/format';
import { useCategories, useSummary } from '@/lib/queries';

export const Route = createFileRoute('/')({
  component: Dashboard,
});

function Dashboard() {
  const [month, setMonth] = useState(monthKey(new Date()));
  const [donutMonth, setDonutMonth] = useState(monthKey(new Date()));
  const summary = useSummary(month);
  const categories = useCategories();

  const currency = summary.data?.currency ?? 'ARS';
  const byId = new Map((categories.data ?? []).map((c) => [c.id, c]));

  return (
    <div className="flex w-full max-w-5xl flex-col gap-10">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <PageTitle>Resumen</PageTitle>
        <MonthPicker month={month} onChange={setMonth} />
      </header>

      <ErrorText error={summary.error} />

      <section className="flex flex-wrap items-center justify-between gap-6">
        <div className="flex flex-col gap-2">
          <span className="label">Resultado de {monthName(month)}</span>
          <p
            className={`display text-hero ${
              Number(summary.data?.monthly_result ?? 0) < 0
                ? 'text-expense'
                : 'text-income'
            }`}
          >
            {summary.data ? heroMoney(summary.data.monthly_result, currency) : '—'}
          </p>
          <p className="num text-sm text-ink-mute">
            <span className="text-income">
              ingresos {money(summary.data?.total_income ?? 0, currency)}
            </span>
            {'  ·  '}
            <span className="text-expense">
              egresos {money(summary.data?.total_expenses ?? 0, currency)}
            </span>
          </p>
        </div>
        <img
          src={heroImage}
          alt=""
          aria-hidden
          className="h-40 w-auto opacity-90"
        />
      </section>

      <SpendingDonut
        month={donutMonth}
        onMonthChange={setDonutMonth}
        currency={currency}
      />

      <section className="flex flex-col gap-4">
        <header className="flex items-baseline justify-between">
          <h2 className="label">Presupuestos</h2>
          <Link to="/presupuestos" className="text-xs text-link underline-offset-4 hover:underline">
            Administrar
          </Link>
        </header>
        {summary.data && summary.data.budgets.length > 0 ? (
          <div className="flex flex-col gap-5">
            {summary.data.budgets.map((budget) => (
              <BudgetBar
                key={budget.id}
                budget={budget}
                category={byId.get(budget.category_id)}
              />
            ))}
          </div>
        ) : (
          <Empty>Todavía no pusiste presupuestos para este mes.</Empty>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <header className="flex items-baseline justify-between">
          <h2 className="label">Actividad reciente</h2>
          <Link
            to="/transacciones"
            className="text-xs text-link underline-offset-4 hover:underline"
          >
            Ver todo
          </Link>
        </header>
        <TransactionList
          transactions={summary.data?.recent ?? []}
          categories={categories.data ?? []}
          empty="Este mes todavía no tiene movimientos."
        />
      </section>
    </div>
  );
}
