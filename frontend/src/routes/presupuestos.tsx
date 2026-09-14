import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Check, Trash2 } from 'lucide-react';

import BudgetBar from '@/components/budgets/BudgetBar';
import MonthPicker from '@/components/MonthPicker';
import { Button } from '@/components/ui/button';
import { Empty, ErrorText, Field, PageTitle, SelectField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { decimal, monthKey } from '@/lib/format';
import {
  useBudgets,
  useCategories,
  useCreateBudget,
  useDeleteBudget,
  useUpdateBudget,
} from '@/lib/queries';
import type { BudgetProgress, Category } from '@/lib/types';

export const Route = createFileRoute('/presupuestos')({
  component: Presupuestos,
});

function Presupuestos() {
  const [month, setMonth] = useState(monthKey(new Date()));
  const budgets = useBudgets(month);
  const categories = useCategories();
  const byId = new Map((categories.data ?? []).map((c) => [c.id, c]));

  return (
    <div className="flex w-full max-w-3xl flex-col gap-10">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <PageTitle>Presupuestos</PageTitle>
        <MonthPicker month={month} onChange={setMonth} />
      </header>

      <ErrorText error={budgets.error} />

      <section className="flex flex-col gap-6">
        {budgets.data && budgets.data.length > 0 ? (
          budgets.data.map((budget) => (
            <BudgetRow
              key={budget.id}
              budget={budget}
              category={byId.get(budget.category_id)}
            />
          ))
        ) : (
          <Empty>
            Este mes todavía no tiene presupuestos. Poné el primero acá abajo.
          </Empty>
        )}
      </section>

      <NewBudget month={month} budgets={budgets.data ?? []} />
    </div>
  );
}

function BudgetRow({
  budget,
  category,
}: {
  budget: BudgetProgress;
  category?: Category;
}) {
  const [amount, setAmount] = useState(budget.amount);
  const update = useUpdateBudget();
  const remove = useDeleteBudget();
  const changed = amount !== budget.amount;

  return (
    <div className="flex flex-col gap-2">
      <BudgetBar budget={budget} category={category} />
      <div className="flex items-center gap-2">
        <Input
          className="num w-40"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
        <Button
          variant="outline"
          size="sm"
          disabled={!changed || update.isPending}
          onClick={() =>
            update.mutate({
              id: budget.id,
              changes: { amount: decimal(amount) },
            })
          }
        >
          <Check /> Guardar
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Quitar presupuesto"
          disabled={remove.isPending}
          onClick={() => remove.mutate(budget.id)}
        >
          <Trash2 />
        </Button>
        <ErrorText error={update.error ?? remove.error} />
      </div>
    </div>
  );
}

function NewBudget({
  month,
  budgets,
}: {
  month: string;
  budgets: BudgetProgress[];
}) {
  const categories = useCategories();
  const create = useCreateBudget();
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('ARS');

  const taken = new Set(budgets.map((budget) => budget.category_id));
  const options = (categories.data ?? [])
    .filter((category) => category.type === 'expense' && !taken.has(category.id))
    .map((category) => ({ value: category.id, label: category.name }));

  return (
    <form
      className="flex flex-col gap-4 rounded-xl bg-paper-2 p-6"
      onSubmit={(event) => {
        event.preventDefault();
        if (!categoryId || !amount) return;
        create.mutate(
          {
            category_id: categoryId,
            amount: decimal(amount),
            currency,
            month: `${month}-01`,
          },
          {
            onSuccess: () => {
              setAmount('');
              setCategoryId(null);
            },
          },
        );
      }}
    >
      <h2 className="label">Nuevo presupuesto</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Field label="Categoría">
          <SelectField
            value={categoryId}
            onChange={setCategoryId}
            options={options}
            placeholder="Elegí una categoría"
          />
        </Field>
        <Field label="Monto">
          <Input
            className="num"
            inputMode="decimal"
            placeholder="100.000"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </Field>
        <Field label="Moneda">
          <SelectField
            value={currency}
            onChange={setCurrency}
            options={[
              { value: 'ARS', label: 'Pesos (ARS)' },
              { value: 'USD', label: 'Dólares (USD)' },
            ]}
          />
        </Field>
      </div>
      <ErrorText error={create.error} />
      <div className="flex justify-end">
        <Button type="submit" disabled={!categoryId || !amount || create.isPending}>
          Agregar
        </Button>
      </div>
    </form>
  );
}
