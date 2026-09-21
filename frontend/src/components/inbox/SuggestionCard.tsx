import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ErrorText, Field, SelectField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  CURRENCY_OPTIONS,
  decimal,
  longDay,
  money,
  monthName,
  typedAmount,
} from '@/lib/format';
import { useAcceptSuggestion, useRejectSuggestion } from '@/lib/queries';
import type {
  Category,
  Currency,
  SetBudgetPayload,
  Suggestion,
  SuggestionEdits,
} from '@/lib/types';

/**
 * One proposal, said plainly: what it would change, why, and what to do about it.
 *
 * The user decides from this card alone, so it never hides behind "gasto
 * recurrente de marzo" — the amount, the day and the category are all here, and
 * so is the chance to change any of them before saying yes. Rejecting means "no
 * este mes", which is why the reason is optional: most months there isn't one.
 *
 * Each kind says what it is proposing and how it can be edited; everything
 * around that — the rationale, the buttons, the two questions the card can ask
 * — is the same whatever is being proposed.
 */
export default function SuggestionCard({
  suggestion,
  categories = [],
  category,
}: {
  suggestion: Suggestion;
  categories?: Category[];
  category?: Category;
}) {
  // Which question the card is asking, if any: nothing, the edit form, or the
  // reason for saying no.
  const [open, setOpen] = useState<'editing' | 'rejecting' | null>(null);

  const accept = useAcceptSuggestion();
  const rejection = useRejectSuggestion();

  const { amount, currency } = suggestion.payload;
  const working = accept.isPending || rejection.isPending;
  const said = describe(suggestion, category);

  function onAccept(payload?: SuggestionEdits) {
    accept.mutate({ id: suggestion.id, payload });
  }

  return (
    <article className="flex flex-col gap-3 rounded-xl bg-paper-2 p-5">
      <header className="leader">
        <span className="text-sm">{said.title}</span>
        <Badge variant="outline">{said.badge}</Badge>
        <span className="dots" />
        <span className="num text-sm">{money(amount, currency)}</span>
      </header>

      <p className="tag">{said.detail}</p>

      <p className="text-sm text-ink-mute">{suggestion.rationale}</p>

      <ErrorText error={accept.error ?? rejection.error} />

      {open === 'editing' ? (
        suggestion.kind === 'set_budget' ? (
          <BudgetForm
            proposed={suggestion.payload}
            pending={working}
            onCancel={() => setOpen(null)}
            onAccept={onAccept}
          />
        ) : (
          <EditForm
            suggestion={suggestion}
            categories={categories}
            pending={working}
            onCancel={() => setOpen(null)}
            onAccept={onAccept}
          />
        )
      ) : open === 'rejecting' ? (
        <RejectForm
          pending={working}
          onCancel={() => setOpen(null)}
          onReject={(reason) => rejection.mutate({ id: suggestion.id, reason })}
        />
      ) : (
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={working}
            onClick={() => setOpen('rejecting')}
          >
            No este mes
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={working}
            onClick={() => setOpen('editing')}
          >
            Editar
          </Button>
          <Button size="sm" disabled={working} onClick={() => onAccept()}>
            {accept.isPending ? 'Guardando…' : 'Aceptar'}
          </Button>
        </div>
      )}
    </article>
  );
}

/** What each kind of proposal calls itself, in one place. */
function describe(
  suggestion: Suggestion,
  category?: Category,
): { badge: string; title: string; detail: string } {
  if (suggestion.kind === 'set_budget') {
    return {
      badge: 'presupuesto',
      title: category?.name ?? 'Presupuesto',
      detail: `Límite de ${monthName(suggestion.payload.month)}`,
    };
  }
  const { description, date, is_fixed } = suggestion.payload;
  return {
    badge: 'nuevo gasto',
    title: description,
    detail: `${longDay(date)} · ${category?.name ?? 'sin categoría'}${
      is_fixed ? ' · fijo' : ''
    }`,
  };
}

/**
 * The proposed limit, editable.
 *
 * Only the amount: the Category and the month are what the proposal is *about*,
 * and moving either of them would be setting a different Budget, which the
 * Presupuestos screen already does.
 */
function BudgetForm({
  proposed,
  pending,
  onCancel,
  onAccept,
}: {
  proposed: SetBudgetPayload;
  pending: boolean;
  onCancel: () => void;
  onAccept: (payload: Partial<SetBudgetPayload>) => void;
}) {
  const [amount, setAmount] = useState(typedAmount(proposed.amount));

  return (
    <form
      className="flex flex-col gap-4 pt-1"
      onSubmit={(event) => {
        event.preventDefault();
        if (!amount) return;
        onAccept({ amount: decimal(amount) });
      }}
    >
      <Field label="Monto">
        <Input
          required
          inputMode="decimal"
          className="num"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
      </Field>

      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? 'Guardando…' : 'Guardar y aceptar'}
        </Button>
      </div>
    </form>
  );
}

/**
 * The proposal, editable.
 *
 * It sends only what the user changed, so a field left alone keeps exactly what
 * was proposed — including the link to the Recurring Expense, which the card
 * never shows and must never drop.
 */
function EditForm({
  suggestion,
  categories,
  pending,
  onCancel,
  onAccept,
}: {
  suggestion: Suggestion & { kind: 'add_transaction' };
  categories: Category[];
  pending: boolean;
  onCancel: () => void;
  onAccept: (payload: {
    description: string;
    category_id: string;
    amount: string;
    currency: Currency;
    date: string;
    is_fixed: boolean;
  }) => void;
}) {
  const proposed = suggestion.payload;
  const [description, setDescription] = useState(proposed.description);
  const [amount, setAmount] = useState(typedAmount(proposed.amount));
  const [currency, setCurrency] = useState<Currency>(proposed.currency);
  const [categoryId, setCategoryId] = useState<string | null>(
    proposed.category_id,
  );
  const [date, setDate] = useState(proposed.date);
  const [isFixed, setIsFixed] = useState(proposed.is_fixed);

  const options = categories
    .filter((one) => one.type === 'expense')
    .map((one) => ({ value: one.id, label: one.name }));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!categoryId || !amount) return;
    onAccept({
      description,
      category_id: categoryId,
      amount: decimal(amount),
      currency,
      date,
      is_fixed: isFixed,
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 pt-1">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Monto">
          <Input
            required
            inputMode="decimal"
            className="num"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </Field>

        <Field
          label="Moneda"
          hint={currency === 'USD' ? 'La cotización se estima sola.' : undefined}
        >
          <SelectField
            value={currency}
            onChange={(next) => setCurrency(next as Currency)}
            options={CURRENCY_OPTIONS}
          />
        </Field>

        <Field label="Fecha">
          <Input
            type="date"
            required
            className="num"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </Field>

        <Field label="Categoría">
          <SelectField
            value={categoryId}
            onChange={setCategoryId}
            options={options}
          />
        </Field>

        <Field label="Descripción">
          <Input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={isFixed}
          onCheckedChange={(checked) => setIsFixed(checked === true)}
        />
        Es un gasto fijo
      </label>

      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" size="sm" disabled={pending || !categoryId}>
          {pending ? 'Guardando…' : 'Guardar y aceptar'}
        </Button>
      </div>
    </form>
  );
}

/** "No este mes", and why, if the user feels like saying. */
function RejectForm({
  pending,
  onCancel,
  onReject,
}: {
  pending: boolean;
  onCancel: () => void;
  onReject: (reason?: string) => void;
}) {
  const [reason, setReason] = useState('');

  return (
    <form
      className="flex flex-col gap-4 pt-1"
      onSubmit={(event) => {
        event.preventDefault();
        onReject(reason.trim() || undefined);
      }}
    >
      <Field label="Motivo" hint="Opcional. Ayuda a las próximas propuestas.">
        <Input
          maxLength={250}
          placeholder="Este mes no lo pagué"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </Field>

      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" variant="outline" size="sm" disabled={pending}>
          {pending ? 'Guardando…' : 'No este mes'}
        </Button>
      </div>
    </form>
  );
}
