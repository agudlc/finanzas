import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Trash2 } from 'lucide-react';

import ProfileForm from '@/components/settings/ProfileForm';
import { Button } from '@/components/ui/button';
import { Empty, ErrorText, Field, PageTitle, SelectField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { RATE_TYPE_LABEL } from '@/lib/format';
import {
  useCategories,
  useCreateCategory,
  useDeleteCategory,
  useDeleteProfile,
  useDeleteRule,
  useProfiles,
  useRules,
  useSettings,
  useUpdateCategory,
  useUpdateRule,
  useUpdateSettings,
} from '@/lib/queries';
import type { Currency, RateType, TransactionType } from '@/lib/types';

export const Route = createFileRoute('/ajustes')({
  component: Ajustes,
});

function Ajustes() {
  return (
    <div className="flex w-full max-w-3xl flex-col gap-10">
      <PageTitle>Ajustes</PageTitle>
      <Preferences />
      <Separator />
      <Categories />
      <Separator />
      <Profiles />
      <Separator />
      <Rules />
    </div>
  );
}

function Preferences() {
  const settings = useSettings();
  const update = useUpdateSettings();

  return (
    <section className="flex flex-col gap-4">
      <h2 className="label">Preferencias</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Moneda de visualización"
          hint="En qué moneda se muestran los totales y los presupuestos."
        >
          <SelectField
            value={settings.data?.display_currency ?? null}
            onChange={(next) =>
              update.mutate({ display_currency: next as Currency })
            }
            options={[
              { value: 'ARS', label: 'Pesos (ARS)' },
              { value: 'USD', label: 'Dólares (USD)' },
            ]}
          />
        </Field>
        <Field
          label="Cotización por defecto"
          hint="Con cuál se estiman las transacciones en dólares."
        >
          <SelectField
            value={settings.data?.default_rate_type ?? null}
            onChange={(next) =>
              update.mutate({ default_rate_type: next as RateType })
            }
            options={(Object.keys(RATE_TYPE_LABEL) as RateType[]).map((type) => ({
              value: type,
              label: RATE_TYPE_LABEL[type],
            }))}
          />
        </Field>
      </div>
      <ErrorText error={update.error} />
    </section>
  );
}

function Categories() {
  const categories = useCategories();
  const create = useCreateCategory();
  const update = useUpdateCategory();
  const remove = useDeleteCategory();

  const [name, setName] = useState('');
  const [color, setColor] = useState('#8a8170');
  const [type, setType] = useState<TransactionType>('expense');

  return (
    <section className="flex flex-col gap-4">
      <h2 className="label">Categorías</h2>

      <ul className="w-full">
        {(categories.data ?? []).map((category) => (
          <li
            key={category.id}
            className="flex items-center gap-3 border-b border-rule-soft py-2"
          >
            <input
              type="color"
              aria-label={`Color de ${category.name}`}
              className="size-6 cursor-pointer rounded-xs border border-rule bg-transparent"
              value={category.color}
              onChange={(event) =>
                update.mutate({
                  id: category.id,
                  changes: { color: event.target.value },
                })
              }
            />
            <Input
              className="max-w-64"
              defaultValue={category.name}
              onBlur={(event) => {
                const next = event.target.value.trim();
                if (next && next !== category.name) {
                  update.mutate({ id: category.id, changes: { name: next } });
                }
              }}
            />
            <span className="tag">
              {category.type === 'expense' ? 'egreso' : 'ingreso'}
            </span>
            <span className="flex-1" />
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Eliminar ${category.name}`}
              onClick={() => remove.mutate(category.id)}
            >
              <Trash2 />
            </Button>
          </li>
        ))}
      </ul>

      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          create.mutate(
            { name: name.trim(), color, type },
            { onSuccess: () => setName('') },
          );
        }}
      >
        <Field label="Nueva categoría">
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Tipo">
          <SelectField
            value={type}
            onChange={(next) => setType(next as TransactionType)}
            options={[
              { value: 'expense', label: 'Egreso' },
              { value: 'income', label: 'Ingreso' },
            ]}
          />
        </Field>
        <Field label="Color">
          <input
            type="color"
            className="h-8 w-16 cursor-pointer rounded-sm border border-rule bg-transparent"
            value={color}
            onChange={(event) => setColor(event.target.value)}
          />
        </Field>
        <Button type="submit" disabled={!name.trim() || create.isPending}>
          Agregar
        </Button>
      </form>

      <ErrorText error={create.error ?? update.error ?? remove.error} />
    </section>
  );
}

function Profiles() {
  const profiles = useProfiles();
  const remove = useDeleteProfile();
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <section className="flex flex-col gap-4">
      <h2 className="label">Perfiles de importación</h2>

      {profiles.data && profiles.data.length > 0 ? (
        <ul className="w-full">
          {profiles.data.map((profile) => (
            <li key={profile.id} className="border-b border-rule-soft py-2">
              <div className="leader">
                <span className="text-sm">{profile.name}</span>
                <span className="tag">{profile.source}</span>
                <span className="dots" />
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() =>
                    setEditing(editing === profile.id ? null : profile.id)
                  }
                >
                  {editing === profile.id ? 'Cerrar' : 'Editar'}
                </Button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Eliminar ${profile.name}`}
                  onClick={() => remove.mutate(profile.id)}
                >
                  <Trash2 />
                </Button>
              </div>
              {editing === profile.id ? (
                <div className="py-4">
                  <ProfileForm
                    profile={profile}
                    onDone={() => setEditing(null)}
                  />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <Empty>
          Todavía no hay perfiles. Creá uno con un export real a mano.
        </Empty>
      )}

      <ErrorText error={remove.error} />
      <ProfileForm />
    </section>
  );
}

function Rules() {
  const rules = useRules();
  const categories = useCategories();
  const update = useUpdateRule();
  const remove = useDeleteRule();

  const options = (categories.data ?? []).map((category) => ({
    value: category.id,
    label: category.name,
  }));

  return (
    <section className="flex flex-col gap-4">
      <h2 className="label">Reglas de categorización</h2>
      {rules.data && rules.data.length > 0 ? (
        <ul className="w-full">
          {rules.data.map((rule) => (
            <li
              key={rule.id}
              className="flex flex-wrap items-center gap-3 border-b border-rule-soft py-2"
            >
              <Input
                className="max-w-64"
                defaultValue={rule.pattern}
                onBlur={(event) => {
                  const next = event.target.value.trim();
                  if (next && next !== rule.pattern) {
                    update.mutate({ id: rule.id, changes: { pattern: next } });
                  }
                }}
              />
              <span className="text-sm text-ink-mute">→</span>
              <SelectField
                className="w-48"
                value={rule.category_id}
                onChange={(next) =>
                  update.mutate({ id: rule.id, changes: { category_id: next } })
                }
                options={options}
              />
              <span className="flex-1" />
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Eliminar la regla ${rule.pattern}`}
                onClick={() => remove.mutate(rule.id)}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>
          Las reglas se aprenden solas cuando marcás «recordar» al importar.
        </Empty>
      )}
      <ErrorText error={update.error ?? remove.error} />
    </section>
  );
}
