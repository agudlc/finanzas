import { useState } from 'react';
import { Trash2, Undo2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { ErrorText } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  RATE_TYPE_LABEL,
  decimal,
  longDay,
  money,
  shortDay,
} from '@/lib/format';
import {
  useCreateRefund,
  useDeleteTransaction,
  useUpdateTransaction,
} from '@/lib/queries';
import type { Category, Transaction } from '@/lib/types';
import { cn } from '@/lib/utils';

/** Estimated figures are dashed and faded, so what may still move is obvious. */
function Estimated({ children }: { children: React.ReactNode }) {
  return (
    <span
      title="Estimado: todavía puede cambiar"
      className="border-b border-dashed border-ink-faint text-ink-mute"
    >
      {children}
    </span>
  );
}

/**
 * One lean row that opens in place.
 *
 * Closed it is a date, a description and a figure. Open it shows everything
 * else and the few things that can be done to it.
 */
export default function TransactionRow({
  transaction,
  category,
}: {
  transaction: Transaction;
  category?: Category;
}) {
  const [open, setOpen] = useState(false);
  const income = transaction.type === 'income';
  const refund = Number(transaction.amount) < 0;
  const estimated = transaction.amount_status === 'estimated';

  return (
    <li className="border-b border-rule-soft last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-baseline gap-3 py-2.5 text-left hover:bg-paper-2/60"
      >
        <span className="num w-14 shrink-0 text-xs text-ink-faint">
          {shortDay(transaction.date)}
        </span>
        <span className="flex-1 truncate text-sm">
          {transaction.description || category?.name || 'Sin descripción'}
          {transaction.installment_number ? (
            <span className="tag ml-2">
              cuota {transaction.installment_number}
            </span>
          ) : null}
          {refund ? <span className="tag ml-2">reintegro</span> : null}
          {transaction.is_fixed ? <span className="tag ml-2">fijo</span> : null}
        </span>
        <span
          className="hidden w-28 shrink-0 truncate text-xs text-ink-mute sm:block"
          style={{ color: category?.color }}
        >
          {category?.name}
        </span>
        {/* `income` is the colour of an Income. A Refund is a negative
            Expense, never an Income, so it stays in plain ink. */}
        <span
          className={cn(
            'num w-40 shrink-0 text-right text-sm',
            income ? 'text-income' : 'text-ink',
          )}
        >
          {estimated ? (
            <Estimated>{money(transaction.amount, transaction.currency)}</Estimated>
          ) : (
            money(transaction.amount, transaction.currency)
          )}
        </span>
      </button>

      {open ? <Details transaction={transaction} category={category} /> : null}
    </li>
  );
}

function Details({
  transaction,
  category,
}: {
  transaction: Transaction;
  category?: Category;
}) {
  const update = useUpdateTransaction();
  const remove = useDeleteTransaction();
  const refund = useCreateRefund();
  const [rate, setRate] = useState('');
  const [amount, setAmount] = useState(transaction.amount);
  const [refundAmount, setRefundAmount] = useState('');

  const rateIsEstimated = transaction.exchange_rate_status === 'estimated';
  const isRefund = Number(transaction.amount) < 0;

  return (
    <div className="flex flex-col gap-4 bg-paper-2 px-3 py-4 text-sm">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        <Detail term="Fecha">{longDay(transaction.date)}</Detail>
        <Detail term="Categoría">{category?.name ?? '—'}</Detail>
        <Detail term="Tipo">
          {transaction.type === 'income' ? 'Ingreso' : 'Egreso'}
        </Detail>
        <Detail term="Moneda">{transaction.currency}</Detail>
        {transaction.exchange_rate ? (
          <Detail term="Cotización">
            <span className={cn('num', rateIsEstimated && 'text-ink-mute')}>
              {Number(transaction.exchange_rate).toLocaleString('es-AR')}
            </span>{' '}
            {transaction.exchange_rate_type
              ? RATE_TYPE_LABEL[transaction.exchange_rate_type]
              : ''}
            {rateIsEstimated ? ' (estimada)' : ' (confirmada)'}
          </Detail>
        ) : null}
        {transaction.notes ? (
          <Detail term="Notas" className="col-span-2">
            {transaction.notes}
          </Detail>
        ) : null}
      </dl>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="label">Monto</span>
          <Input
            className="num w-40"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <Button
          variant="outline"
          disabled={amount === transaction.amount || update.isPending}
          onClick={() =>
            update.mutate({ id: transaction.id, changes: { amount } })
          }
        >
          Guardar monto
        </Button>

        {rateIsEstimated ? (
          <>
            <label className="flex flex-col gap-1">
              <span className="label">Cotización real</span>
              <Input
                className="num w-40"
                placeholder="1620,50"
                value={rate}
                onChange={(event) => setRate(event.target.value)}
              />
            </label>
            <Button
              variant="outline"
              disabled={!rate || update.isPending}
              onClick={() =>
                update.mutate({
                  id: transaction.id,
                  changes: {
                    exchange_rate: decimal(rate),
                    exchange_rate_status: 'confirmed',
                  },
                })
              }
            >
              Confirmar cotización
            </Button>
          </>
        ) : null}
      </div>

      {transaction.type === 'expense' && !isRefund ? (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="label">Reintegro</span>
            <Input
              className="num w-40"
              placeholder="0,00"
              value={refundAmount}
              onChange={(event) => setRefundAmount(event.target.value)}
            />
          </label>
          <Button
            variant="outline"
            disabled={!refundAmount || refund.isPending}
            onClick={() =>
              refund.mutate(
                {
                  id: transaction.id,
                  body: {
                    amount: decimal(refundAmount),
                    date: transaction.date,
                  },
                },
                { onSuccess: () => setRefundAmount('') },
              )
            }
          >
            <Undo2 /> Registrar reintegro
          </Button>
        </div>
      ) : null}

      <div>
        <Button
          variant="destructive"
          size="sm"
          disabled={remove.isPending}
          onClick={() => remove.mutate(transaction.id)}
        >
          <Trash2 /> Eliminar
        </Button>
      </div>

      <ErrorText error={update.error ?? remove.error ?? refund.error} />
    </div>
  );
}

function Detail({
  term,
  children,
  className,
}: {
  term: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="label">{term}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}
