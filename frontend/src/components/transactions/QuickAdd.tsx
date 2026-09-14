import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ErrorText, Field, SelectField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { RATE_TYPE_LABEL, decimal, today } from '@/lib/format';
import {
  useCategories,
  useCreatePurchase,
  useCreateTransaction,
} from '@/lib/queries';
import type { Currency, RateType, TransactionType } from '@/lib/types';

type Kind = 'expense' | 'income' | 'refund' | 'installments';

const KINDS: { value: Kind; label: string }[] = [
  { value: 'expense', label: 'Egreso' },
  { value: 'income', label: 'Ingreso' },
  { value: 'refund', label: 'Reintegro' },
  { value: 'installments', label: 'En cuotas' },
];

const CURRENCIES = [
  { value: 'ARS', label: 'Pesos (ARS)' },
  { value: 'USD', label: 'Dólares (USD)' },
];

const RATE_TYPES = (Object.keys(RATE_TYPE_LABEL) as RateType[])
  .filter((type) => type !== 'manual')
  .map((type) => ({ value: type, label: RATE_TYPE_LABEL[type] }));

/**
 * Logging a movement in seconds.
 *
 * The kind chosen at the top decides which Categories are on offer, so an
 * Expense can never be filed under an income Category by accident.
 */
export default function QuickAdd({ onDone }: { onDone?: () => void }) {
  const [kind, setKind] = useState<Kind>('expense');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState<Currency>('ARS');
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [date, setDate] = useState(today());
  const [description, setDescription] = useState('');
  const [notes, setNotes] = useState('');
  const [isFixed, setIsFixed] = useState(false);
  const [rateType, setRateType] = useState<string | null>(null);
  const [rate, setRate] = useState('');
  const [installments, setInstallments] = useState('3');

  const categories = useCategories();
  const createTransaction = useCreateTransaction();
  const createPurchase = useCreatePurchase();

  const wantedType: TransactionType = kind === 'income' ? 'income' : 'expense';
  const options = (categories.data ?? [])
    .filter((category) => category.type === wantedType)
    .map((category) => ({ value: category.id, label: category.name }));

  const pending = createTransaction.isPending || createPurchase.isPending;
  const error = createTransaction.error ?? createPurchase.error;

  function reset() {
    setAmount('');
    setDescription('');
    setNotes('');
    setRate('');
    setIsFixed(false);
    onDone?.();
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!categoryId || !amount) return;

    const usd = currency === 'USD';
    const rateFields = usd
      ? {
          exchange_rate_type: rate ? 'manual' : rateType,
          exchange_rate: rate ? decimal(rate) : undefined,
          exchange_rate_status: rate ? 'confirmed' : undefined,
        }
      : {};

    if (kind === 'installments') {
      createPurchase.mutate(
        {
          description: description || 'Compra en cuotas',
          total_amount: decimal(amount),
          installments: Number(installments),
          category_id: categoryId,
          currency,
          purchase_date: date,
          exchange_rate_type: usd ? rateType : null,
        },
        { onSuccess: reset },
      );
      return;
    }

    createTransaction.mutate(
      {
        amount: kind === 'refund' ? `-${decimal(amount)}` : decimal(amount),
        currency,
        type: wantedType,
        category_id: categoryId,
        date,
        description: description || null,
        notes: notes || null,
        is_fixed: isFixed,
        ...rateFields,
      },
      { onSuccess: reset },
    );
  }

  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-4">
      <Tabs
        value={kind}
        onValueChange={(next) => {
          setKind(next as Kind);
          setCategoryId(null);
        }}
      >
        <TabsList>
          {KINDS.map((option) => (
            <TabsTrigger key={option.value} value={option.value}>
              {option.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label={kind === 'installments' ? 'Total de la compra' : 'Monto'}
          hint={kind === 'refund' ? 'Se guarda como un egreso negativo.' : undefined}
        >
          <Input
            required
            inputMode="decimal"
            placeholder="12.500,50"
            className="num"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </Field>

        <Field label="Moneda">
          <SelectField
            value={currency}
            onChange={(next) => setCurrency(next as Currency)}
            options={CURRENCIES}
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

        <Field label={kind === 'installments' ? 'Fecha de compra' : 'Fecha'}>
          <Input
            type="date"
            required
            className="num"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </Field>

        {kind === 'installments' ? (
          <Field label="Cantidad de cuotas">
            <Input
              type="number"
              min={1}
              max={60}
              required
              className="num"
              value={installments}
              onChange={(event) => setInstallments(event.target.value)}
            />
          </Field>
        ) : null}

        {currency === 'USD' ? (
          <>
            <Field
              label="Tipo de cotización"
              hint="Si lo dejás vacío se usa el de Ajustes."
            >
              <SelectField
                value={rateType}
                onChange={setRateType}
                options={RATE_TYPES}
                placeholder="El de Ajustes"
              />
            </Field>
            {kind !== 'installments' ? (
              <Field
                label="Cotización"
                hint="Si la sabés, escribila; si no, se estima sola."
              >
                <Input
                  inputMode="decimal"
                  placeholder="1.620,50"
                  className="num"
                  value={rate}
                  onChange={(event) => setRate(event.target.value)}
                />
              </Field>
            ) : null}
          </>
        ) : null}

        <Field label="Descripción" className="sm:col-span-2">
          <Input
            placeholder="Supermercado Coto"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        {kind !== 'installments' ? (
          <Field label="Notas" className="sm:col-span-2">
            <Textarea
              rows={2}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </Field>
        ) : null}
      </div>

      {kind === 'expense' ? (
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={isFixed}
            onCheckedChange={(checked) => setIsFixed(checked === true)}
          />
          Es un gasto fijo
        </label>
      ) : null}

      <ErrorText error={error} />

      <div className="flex justify-end">
        <Button type="submit" disabled={pending || !categoryId || !amount}>
          {pending ? 'Guardando…' : 'Guardar'}
        </Button>
      </div>
    </form>
  );
}
