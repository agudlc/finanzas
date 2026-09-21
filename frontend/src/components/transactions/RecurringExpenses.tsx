import { useState } from 'react';
import { Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Empty, ErrorText, Field, SelectField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { CURRENCY_OPTIONS, decimal, money, typedAmount } from '@/lib/format';
import {
  useCategories,
  useCreateRecurringExpense,
  useDeleteRecurringExpense,
  useRecurringExpenses,
  useUpdateRecurringExpense,
} from '@/lib/queries';
import type { AdjustmentRule, Currency, RecurringExpense } from '@/lib/types';

/** The kinds of Adjustment Rule, plus the "no rule at all" the form needs. */
const ADJUSTMENT_OPTIONS = [
  { value: 'none', label: 'No se ajusta' },
  { value: 'percentage', label: 'Por un porcentaje fijo' },
  { value: 'index', label: 'Por inflación (IPC)' },
];

/** How a rule reads in a list: "ajusta 10% cada 6 meses". */
function adjustmentLabel(rule: AdjustmentRule): string {
  const by =
    rule.kind === 'percentage'
      ? `${Number(rule.percentage)}%`
      : `por ${rule.index_name}`;
  return `ajusta ${by} cada ${rule.period_months} ${
    rule.period_months === 1 ? 'mes' : 'meses'
  }`;
}

/**
 * The Expenses expected every month, next to the Transactions they will produce.
 *
 * A template records nothing by itself: each month it turns into a suggestion.
 * That is why pausing one is a button of its own — going without a payment for
 * a while should not throw away the template that describes it.
 */
export default function RecurringExpenses() {
  const [editing, setEditing] = useState<RecurringExpense | null>(null);
  const [adding, setAdding] = useState(false);

  const templates = useRecurringExpenses();
  const categories = useCategories();
  const update = useUpdateRecurringExpense();
  const remove = useDeleteRecurringExpense();
  const byId = new Map((categories.data ?? []).map((one) => [one.id, one]));

  const open = adding || editing !== null;

  function close() {
    setAdding(false);
    setEditing(null);
  }

  return (
    <section className="flex flex-col gap-2">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="label">Gastos recurrentes</h2>
        <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
          <Plus /> Nuevo
        </Button>
      </header>

      {templates.data && templates.data.length > 0 ? (
        <ul className="w-full">
          {templates.data.map((template) => (
            <li
              key={template.id}
              className="leader border-b border-rule-soft py-2.5"
            >
              <span
                className={
                  template.is_active ? 'text-sm' : 'text-sm text-ink-faint'
                }
              >
                {template.description}
              </span>
              <span className="tag">
                día {template.expected_day} ·{' '}
                {byId.get(template.category_id)?.name ?? 'sin categoría'}
                {template.is_fixed ? ' · fijo' : ''}
                {template.adjustment
                  ? ` · ${adjustmentLabel(template.adjustment)}`
                  : ''}
                {template.is_active ? '' : ' · en pausa'}
              </span>
              <span className="dots" />
              <span className="num text-sm">
                {money(template.reference_amount, template.currency)}
              </span>
              <Button variant="ghost" size="xs" onClick={() => setEditing(template)}>
                Editar
              </Button>
              <Button
                variant="ghost"
                size="xs"
                disabled={update.isPending}
                onClick={() =>
                  update.mutate({
                    id: template.id,
                    changes: { is_active: !template.is_active },
                  })
                }
              >
                {template.is_active ? 'Pausar' : 'Reactivar'}
              </Button>
              <Button
                variant="ghost"
                size="xs"
                disabled={remove.isPending}
                onClick={() => remove.mutate(template.id)}
              >
                Eliminar
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Todavía no describiste ningún gasto que se repita cada mes.</Empty>
      )}

      <ErrorText error={update.error ?? remove.error} />

      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) close();
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editing ? 'Editar gasto recurrente' : 'Nuevo gasto recurrente'}
            </DialogTitle>
            <DialogDescription>
              Un gasto que esperás todos los meses. No se carga solo: cada mes te
              lo vamos a proponer.
            </DialogDescription>
          </DialogHeader>
          {open ? (
            <RecurringForm
              key={editing?.id ?? 'nuevo'}
              template={editing}
              onDone={close}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function RecurringForm({
  template,
  onDone,
}: {
  template: RecurringExpense | null;
  onDone: () => void;
}) {
  const [description, setDescription] = useState(template?.description ?? '');
  const [amount, setAmount] = useState(
    template ? typedAmount(template.reference_amount) : '',
  );
  const [currency, setCurrency] = useState<Currency>(template?.currency ?? 'ARS');
  const [categoryId, setCategoryId] = useState<string | null>(
    template?.category_id ?? null,
  );
  const [day, setDay] = useState(String(template?.expected_day ?? 1));
  const [isFixed, setIsFixed] = useState(template?.is_fixed ?? false);
  const [adjustmentKind, setAdjustmentKind] = useState(
    template?.adjustment?.kind ?? 'none',
  );
  const [period, setPeriod] = useState(
    String(template?.adjustment?.period_months ?? 6),
  );
  const [percentage, setPercentage] = useState(
    template?.adjustment?.percentage ? typedAmount(template.adjustment.percentage) : '',
  );
  // A month input speaks "2026-01"; the API stores the month's first day.
  const [startMonth, setStartMonth] = useState(
    (template?.adjustment?.start_month ?? '').slice(0, 7),
  );

  const categories = useCategories();
  const create = useCreateRecurringExpense();
  const update = useUpdateRecurringExpense();

  // A template can only produce an Expense, so only expense Categories fit.
  const options = (categories.data ?? [])
    .filter((category) => category.type === 'expense')
    .map((category) => ({ value: category.id, label: category.name }));

  const pending = create.isPending || update.isPending;
  const error = create.error ?? update.error;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!categoryId || !amount) return;

    const body = {
      description,
      category_id: categoryId,
      reference_amount: decimal(amount),
      expected_day: Number(day),
      currency,
      is_fixed: isFixed,
      adjustment:
        adjustmentKind === 'none'
          ? null
          : {
              kind: adjustmentKind,
              period_months: Number(period),
              start_month: `${startMonth}-01`,
              ...(adjustmentKind === 'percentage'
                ? { percentage: decimal(percentage) }
                : {}),
            },
    };

    if (template) {
      update.mutate({ id: template.id, changes: body }, { onSuccess: onDone });
      return;
    }
    create.mutate(body, { onSuccess: onDone });
  }

  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Descripción" className="sm:col-span-2">
          <Input
            required
            placeholder="Alquiler"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        <Field
          label="Monto de referencia"
          hint="Se usa hasta que haya un movimiento cargado desde esta plantilla."
        >
          <Input
            required
            inputMode="decimal"
            placeholder="450.000,00"
            className="num"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </Field>

        <Field label="Moneda">
          <SelectField
            value={currency}
            onChange={(next) => setCurrency(next as Currency)}
            options={CURRENCY_OPTIONS}
          />
        </Field>

        <Field label="Categoría">
          <SelectField
            value={categoryId}
            onChange={setCategoryId}
            options={options}
            placeholder="Elegí una categoría"
          />
        </Field>

        <Field label="Día esperado" hint="Del 1 al 31.">
          <Input
            type="number"
            min={1}
            max={31}
            required
            className="num"
            value={day}
            onChange={(event) => setDay(event.target.value)}
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Ajuste"
          className="sm:col-span-2"
          hint="Como en un contrato de alquiler: cada tantos meses, por un porcentaje o por el IPC."
        >
          <SelectField
            value={adjustmentKind}
            onChange={(next) =>
              setAdjustmentKind(next as AdjustmentRule['kind'] | 'none')
            }
            options={ADJUSTMENT_OPTIONS}
          />
        </Field>

        {adjustmentKind === 'none' ? null : (
          <>
            <Field label="Cada cuántos meses">
              <Input
                type="number"
                min={1}
                required
                className="num"
                value={period}
                onChange={(event) => setPeriod(event.target.value)}
              />
            </Field>

            <Field
              label="Desde el mes"
              hint="El mes en que arranca el ciclo; el primer ajuste cae un período después."
            >
              <Input
                type="month"
                required
                className="num"
                value={startMonth}
                onChange={(event) => setStartMonth(event.target.value)}
              />
            </Field>

            {adjustmentKind === 'percentage' ? (
              <Field label="Porcentaje">
                <Input
                  required
                  inputMode="decimal"
                  placeholder="10,00"
                  className="num"
                  value={percentage}
                  onChange={(event) => setPercentage(event.target.value)}
                />
              </Field>
            ) : null}
          </>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={isFixed}
          onCheckedChange={(checked) => setIsFixed(checked === true)}
        />
        Es un gasto fijo
      </label>

      <ErrorText error={error} />

      <div className="flex justify-end">
        <Button
          type="submit"
          disabled={
            pending ||
            !categoryId ||
            !amount ||
            (adjustmentKind !== 'none' && !startMonth) ||
            (adjustmentKind === 'percentage' && !percentage)
          }
        >
          {pending ? 'Guardando…' : 'Guardar'}
        </Button>
      </div>
    </form>
  );
}
