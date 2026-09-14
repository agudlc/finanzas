import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Plus, Upload } from 'lucide-react';

import ImportDialog from '@/components/transactions/ImportDialog';
import QuickAdd from '@/components/transactions/QuickAdd';
import TransactionList from '@/components/transactions/TransactionList';
import MonthPicker from '@/components/MonthPicker';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Empty, PageTitle, SelectField } from '@/components/ui/field';
import { monthKey, today } from '@/lib/format';
import {
  useCategories,
  useDeletePurchase,
  useImports,
  useProfiles,
  usePurchases,
  useTransactions,
  useUndoImport,
} from '@/lib/queries';

export const Route = createFileRoute('/transacciones')({
  component: Transacciones,
});

const ANY = 'todas';

function Transacciones() {
  const [month, setMonth] = useState(monthKey(new Date()));
  const [type, setType] = useState(ANY);
  const [categoryId, setCategoryId] = useState(ANY);
  const [currency, setCurrency] = useState(ANY);
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);

  const categories = useCategories();
  const todays = useTransactions({ date: today() });
  const listed = useTransactions({
    month,
    type: type === ANY ? undefined : type,
    category_id: categoryId === ANY ? undefined : categoryId,
    currency: currency === ANY ? undefined : currency,
  });

  const categoryOptions = [
    { value: ANY, label: 'Todas las categorías' },
    ...(categories.data ?? []).map((category) => ({
      value: category.id,
      label: category.name,
    })),
  ];

  return (
    <div className="flex w-full max-w-5xl flex-col gap-10">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <PageTitle>Transacciones</PageTitle>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setImporting(true)}>
            <Upload /> Importar
          </Button>
          <Button onClick={() => setAdding(true)}>
            <Plus /> Cargar
          </Button>
        </div>
      </header>

      <section className="flex flex-col gap-2">
        <h2 className="label">Hoy</h2>
        <TransactionList
          transactions={todays.data ?? []}
          categories={categories.data ?? []}
          empty="Todavía no cargaste nada hoy."
        />
      </section>

      <section className="flex flex-col gap-4">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="label">Movimientos del mes</h2>
          <MonthPicker month={month} onChange={setMonth} />
        </header>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <SelectField
            value={type}
            onChange={setType}
            options={[
              { value: ANY, label: 'Todos los tipos' },
              { value: 'expense', label: 'Egresos' },
              { value: 'income', label: 'Ingresos' },
            ]}
          />
          <SelectField
            value={categoryId}
            onChange={setCategoryId}
            options={categoryOptions}
          />
          <SelectField
            value={currency}
            onChange={setCurrency}
            options={[
              { value: ANY, label: 'Todas las monedas' },
              { value: 'ARS', label: 'Pesos' },
              { value: 'USD', label: 'Dólares' },
            ]}
          />
        </div>

        <TransactionList
          transactions={listed.data ?? []}
          categories={categories.data ?? []}
          empty="No hay movimientos con estos filtros."
        />
      </section>

      <InstallmentPurchases />
      <ImportHistory />

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Cargar movimiento</DialogTitle>
            <DialogDescription>
              Un egreso, un ingreso, un reintegro o una compra en cuotas.
            </DialogDescription>
          </DialogHeader>
          <QuickAdd onDone={() => setAdding(false)} />
        </DialogContent>
      </Dialog>

      <Dialog open={importing} onOpenChange={setImporting}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>Importar un export</DialogTitle>
            <DialogDescription>
              Nada se guarda hasta que revises todas las filas.
            </DialogDescription>
          </DialogHeader>
          <ImportDialog onDone={() => setImporting(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function InstallmentPurchases() {
  const purchases = usePurchases();
  const categories = useCategories();
  const remove = useDeletePurchase();
  const byId = new Map((categories.data ?? []).map((c) => [c.id, c]));

  return (
    <section className="flex flex-col gap-2">
      <h2 className="label">Compras en cuotas</h2>
      {purchases.data && purchases.data.length > 0 ? (
        <ul className="w-full">
          {purchases.data.map((purchase) => (
            <li
              key={purchase.id}
              className="leader border-b border-rule-soft py-2.5"
            >
              <span className="text-sm">{purchase.description}</span>
              <span className="tag">
                {purchase.installments} cuotas ·{' '}
                {byId.get(purchase.category_id)?.name}
              </span>
              <span className="dots" />
              <span className="num text-sm">
                {purchase.currency === 'USD' ? 'US$' : '$'}{' '}
                {Number(purchase.total_amount).toLocaleString('es-AR')}
              </span>
              <Button
                variant="ghost"
                size="xs"
                disabled={remove.isPending}
                onClick={() => remove.mutate(purchase.id)}
              >
                Eliminar
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>No hay compras en cuotas.</Empty>
      )}
    </section>
  );
}

function ImportHistory() {
  const imports = useImports();
  const profiles = useProfilesById();
  const undo = useUndoImport();

  if (!imports.data || imports.data.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="label">Importaciones</h2>
      <ul className="w-full">
        {imports.data.map((record) => (
          <li key={record.id} className="leader border-b border-rule-soft py-2.5">
            <span className="text-sm">{record.filename}</span>
            <span className="tag">
              {profiles.get(record.profile_id) ?? 'perfil'} ·{' '}
              {record.imported_count} importadas · {record.skipped_count} salteadas
            </span>
            <span className="dots" />
            <Button
              variant="ghost"
              size="xs"
              disabled={undo.isPending}
              onClick={() => undo.mutate(record.id)}
            >
              Deshacer
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function useProfilesById(): Map<string, string> {
  const profiles = useProfiles();
  return new Map((profiles.data ?? []).map((p) => [p.id, p.name]));
}
