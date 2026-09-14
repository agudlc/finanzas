import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ErrorText, Field, SelectField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useCreateProfile, useUpdateProfile } from '@/lib/queries';
import type {
  ImportProfile,
  NumberFormat,
  SignConvention,
} from '@/lib/types';

const NUMBER_FORMATS = [
  { value: 'comma_decimal', label: '1.234,56 (coma decimal)' },
  { value: 'dot_decimal', label: '1,234.56 (punto decimal)' },
];

const SIGN_CONVENTIONS = [
  { value: 'negative_is_expense', label: 'Negativo = egreso' },
  { value: 'positive_is_expense', label: 'Positivo = egreso' },
  { value: 'debit_credit_columns', label: 'Columnas débito / crédito' },
];

const EMPTY = {
  name: '',
  source: '',
  date_format: '%d/%m/%Y',
  number_format: 'comma_decimal' as NumberFormat,
  sign_convention: 'debit_credit_columns' as SignConvention,
  date: '',
  description: '',
  amount: '',
  debit: '',
  credit: '',
  currency: '',
  type: '',
  ignore_patterns: '',
};

function from(profile: ImportProfile): typeof EMPTY {
  return {
    name: profile.name,
    source: profile.source,
    date_format: profile.date_format,
    number_format: profile.number_format,
    sign_convention: profile.sign_convention,
    date: profile.column_mapping.date,
    description: profile.column_mapping.description,
    amount: profile.column_mapping.amount ?? '',
    debit: profile.column_mapping.debit ?? '',
    credit: profile.column_mapping.credit ?? '',
    currency: profile.column_mapping.currency ?? '',
    type: profile.column_mapping.type ?? '',
    ignore_patterns: profile.ignore_patterns.join('\n'),
  };
}

/** Free text when the columns aren't known, a list of them when they are. */
function ColumnField({
  label,
  hint,
  required,
  columns,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  columns?: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      {columns ? (
        <SelectField
          value={value || null}
          onChange={onChange}
          options={[
            ...(required ? [] : [{ value: '', label: 'Ninguna' }]),
            ...columns.map((column) => ({ value: column, label: column })),
          ]}
          placeholder={required ? 'Elegí una columna' : 'Ninguna'}
        />
      ) : (
        <Input
          required={required}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}

/**
 * Describing one source's export format.
 *
 * Neither Mercado Pago nor Lemon documents its export, so this is written with
 * a real file open. When the file's own headings are known they are offered as
 * choices; otherwise the column names are typed in.
 */
export default function ProfileForm({
  profile,
  columns,
  onDone,
}: {
  profile?: ImportProfile;
  columns?: string[];
  onDone?: (profile: ImportProfile) => void;
}) {
  const [form, setForm] = useState(profile ? from(profile) : EMPTY);
  const create = useCreateProfile();
  const update = useUpdateProfile();
  const saving = create.isPending || update.isPending;

  const debitCredit = form.sign_convention === 'debit_credit_columns';

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const body = {
      name: form.name.trim(),
      source: form.source.trim(),
      date_format: form.date_format.trim(),
      number_format: form.number_format,
      sign_convention: form.sign_convention,
      column_mapping: {
        date: form.date.trim(),
        description: form.description.trim(),
        amount: debitCredit ? null : form.amount.trim() || null,
        debit: debitCredit ? form.debit.trim() || null : null,
        credit: debitCredit ? form.credit.trim() || null : null,
        currency: form.currency.trim() || null,
        type: form.type.trim() || null,
      },
      ignore_patterns: form.ignore_patterns
        .split('\n')
        .map((pattern) => pattern.trim())
        .filter(Boolean),
    };

    if (profile) {
      update.mutate({ id: profile.id, changes: body }, { onSuccess: onDone });
    } else {
      create.mutate(body, {
        onSuccess: (created) => {
          setForm(EMPTY);
          onDone?.(created);
        },
      });
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 rounded-xl bg-paper-2 p-6">
      <h3 className="label">
        {profile ? `Editar ${profile.name}` : 'Nuevo perfil de importación'}
      </h3>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Nombre">
          <Input
            required
            value={form.name}
            onChange={(event) => set('name', event.target.value)}
          />
        </Field>
        <Field label="Fuente" hint="mercadopago, lemon…">
          <Input
            required
            value={form.source}
            onChange={(event) => set('source', event.target.value)}
          />
        </Field>

        <Field label="Formato de fecha" hint="Por ejemplo %d/%m/%Y">
          <Input
            required
            className="num"
            value={form.date_format}
            onChange={(event) => set('date_format', event.target.value)}
          />
        </Field>
        <Field label="Formato de números">
          <SelectField
            value={form.number_format}
            onChange={(next) => set('number_format', next as NumberFormat)}
            options={NUMBER_FORMATS}
          />
        </Field>

        <Field label="Convención de signo" className="sm:col-span-2">
          <SelectField
            value={form.sign_convention}
            onChange={(next) => set('sign_convention', next as SignConvention)}
            options={SIGN_CONVENTIONS}
          />
        </Field>

        <ColumnField
          label="Columna de fecha"
          required
          columns={columns}
          value={form.date}
          onChange={(next) => set('date', next)}
        />
        <ColumnField
          label="Columna de descripción"
          required
          columns={columns}
          value={form.description}
          onChange={(next) => set('description', next)}
        />

        {debitCredit ? (
          <>
            <ColumnField
              label="Columna de débito"
              required
              columns={columns}
              value={form.debit}
              onChange={(next) => set('debit', next)}
            />
            <ColumnField
              label="Columna de crédito"
              required
              columns={columns}
              value={form.credit}
              onChange={(next) => set('credit', next)}
            />
          </>
        ) : (
          <ColumnField
            label="Columna de monto"
            required
            columns={columns}
            value={form.amount}
            onChange={(next) => set('amount', next)}
          />
        )}

        <ColumnField
          label="Columna de moneda"
          hint="Opcional; si falta, se asume ARS."
          columns={columns}
          value={form.currency}
          onChange={(next) => set('currency', next)}
        />
        <ColumnField
          label="Columna de tipo"
          hint="Opcional; la usan los patrones a ignorar."
          columns={columns}
          value={form.type}
          onChange={(next) => set('type', next)}
        />

        <Field
          label="Patrones a ignorar"
          hint="Uno por línea: transferencias, cripto, pagos de tarjeta."
          className="sm:col-span-2"
        >
          <Textarea
            rows={3}
            value={form.ignore_patterns}
            onChange={(event) => set('ignore_patterns', event.target.value)}
          />
        </Field>
      </div>

      <ErrorText error={create.error ?? update.error} />

      <div className="flex justify-end">
        <Button type="submit" disabled={saving}>
          {saving ? 'Guardando…' : profile ? 'Guardar cambios' : 'Crear perfil'}
        </Button>
      </div>
    </form>
  );
}
