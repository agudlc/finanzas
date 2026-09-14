import { useMemo, useState } from 'react';

import ProfileForm from '@/components/settings/ProfileForm';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Empty, ErrorText, Field, SelectField } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { ROW_STATUS_LABEL, money, shortDay } from '@/lib/format';
import {
  useCategories,
  useConfirmImport,
  usePreviewImport,
  useProfiles,
  useReadColumns,
} from '@/lib/queries';
import type { ConfirmRow, ImportPreview, PreviewRow } from '@/lib/types';
import { cn } from '@/lib/utils';

/** The preview row plus the decisions the user made about it. */
type Reviewed = ConfirmRow & { number: number; status: PreviewRow['status'] };

/** The review dropped, leaving only what the confirm endpoint asks for. */
function forConfirming(row: Reviewed): ConfirmRow {
  return {
    date: row.date,
    description: row.description,
    amount: row.amount,
    currency: row.currency,
    type: row.type,
    category_id: row.category_id,
    skip: row.skip,
    is_refund: row.is_refund,
    remember: row.remember,
  };
}

function reviewed(preview: ImportPreview): Reviewed[] {
  return preview.rows.map((row) => ({
    number: row.number,
    status: row.status,
    date: row.date,
    description: row.description,
    amount: row.amount,
    currency: row.currency,
    type: row.type,
    category_id: row.category_id,
    // The rows the preview flagged start skipped; the user can bring any back.
    skip: row.status === 'ignored' || row.status === 'duplicate',
    is_refund: false,
    remember: null,
  }));
}

/**
 * Loading an export, with nothing saved until every row has been seen.
 *
 * The preview is stateless on the server: what comes back is reviewed here and
 * handed back whole when the user confirms.
 */
export default function ImportDialog({ onDone }: { onDone: () => void }) {
  const profiles = useProfiles();
  const categories = useCategories();
  const preview = usePreviewImport();
  const confirm = useConfirmImport();
  const readColumns = useReadColumns();

  const [profileId, setProfileId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<Reviewed[] | null>(null);
  const [filename, setFilename] = useState('');
  // The headings of the chosen file, once the user asks to build a Profile
  // from it rather than from memory.
  const [columns, setColumns] = useState<string[] | null>(null);

  const expenseOptions = (categories.data ?? [])
    .filter((category) => category.type === 'expense')
    .map((category) => ({ value: category.id, label: category.name }));
  const incomeOptions = (categories.data ?? [])
    .filter((category) => category.type === 'income')
    .map((category) => ({ value: category.id, label: category.name }));

  const missing = useMemo(
    () => (rows ?? []).filter((row) => !row.skip && !row.category_id).length,
    [rows],
  );
  const keeping = (rows ?? []).filter((row) => !row.skip).length;

  function change(number: number, changes: Partial<Reviewed>) {
    setRows((current) =>
      (current ?? []).map((row) =>
        row.number === number ? { ...row, ...changes } : row,
      ),
    );
  }

  if (columns !== null && file !== null) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-ink-mute">
          Columnas encontradas en {file.name}: {columns.join(', ')}.
        </p>
        <ProfileForm
          columns={columns}
          onDone={(created) => {
            setProfileId(created.id);
            setColumns(null);
          }}
        />
        <div>
          <Button variant="ghost" onClick={() => setColumns(null)}>
            Volver
          </Button>
        </div>
      </div>
    );
  }

  if (rows === null) {
    return (
      <div className="flex flex-col gap-4">
        <Field label="Perfil de importación">
          <SelectField
            value={profileId}
            onChange={setProfileId}
            options={(profiles.data ?? []).map((profile) => ({
              value: profile.id,
              label: profile.name,
            }))}
            placeholder="Elegí el perfil que lee este archivo"
          />
        </Field>

        <Field label="Archivo" hint="CSV o XLSX exportado desde la fuente.">
          <Input
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </Field>

        {profiles.data && profiles.data.length === 0 ? (
          <Empty>
            Todavía no hay perfiles. Elegí el archivo y creá el primero a partir
            de sus columnas.
          </Empty>
        ) : null}

        <ErrorText error={preview.error ?? readColumns.error} />

        <div className="flex justify-between">
          <Button
            variant="outline"
            disabled={!file || readColumns.isPending}
            onClick={() =>
              readColumns.mutate(file!, {
                onSuccess: (answer) => setColumns(answer.columns),
              })
            }
          >
            {readColumns.isPending ? 'Leyendo…' : 'Crear un perfil con este archivo'}
          </Button>
          <Button
            disabled={!profileId || !file || preview.isPending}
            onClick={() =>
              preview.mutate(
                { profileId: profileId!, file: file! },
                {
                  onSuccess: (answer) => {
                    setRows(reviewed(answer));
                    setFilename(answer.filename);
                  },
                },
              )
            }
          >
            {preview.isPending ? 'Leyendo…' : 'Previsualizar'}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-mute">
        {filename} · se van a guardar <strong>{keeping}</strong> de {rows.length}{' '}
        filas.
      </p>

      <div className="max-h-[50vh] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-paper text-left">
            <tr className="label border-b border-rule">
              <th className="py-2">Guardar</th>
              <th>Fecha</th>
              <th>Descripción</th>
              <th className="text-right">Monto</th>
              <th>Moneda</th>
              <th>Tipo</th>
              <th>Categoría</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.number}
                className={cn(
                  'border-b border-rule-soft',
                  row.skip && 'opacity-50',
                )}
              >
                <td className="py-2">
                  <Checkbox
                    checked={!row.skip}
                    onCheckedChange={(checked) =>
                      change(row.number, { skip: checked !== true })
                    }
                  />
                </td>
                <td className="num whitespace-nowrap text-xs">
                  {shortDay(row.date)}
                </td>
                <td className="max-w-56 truncate">{row.description}</td>
                <td className="num whitespace-nowrap text-right">
                  {money(
                    row.is_refund ? `-${row.amount}` : row.amount,
                    row.currency,
                  )}
                </td>
                <td className="num text-xs">{row.currency}</td>
                <td>
                  <SelectField
                    className="w-32"
                    value={row.is_refund ? 'refund' : row.type}
                    onChange={(next) =>
                      change(row.number, {
                        type: next === 'income' ? 'income' : 'expense',
                        is_refund: next === 'refund',
                        category_id: null,
                      })
                    }
                    options={[
                      { value: 'expense', label: 'Egreso' },
                      { value: 'income', label: 'Ingreso' },
                      { value: 'refund', label: 'Reintegro' },
                    ]}
                  />
                </td>
                <td>
                  <div className="flex flex-col gap-1">
                    <SelectField
                      className="w-40"
                      value={row.category_id}
                      onChange={(next) => change(row.number, { category_id: next })}
                      options={
                        row.type === 'income' ? incomeOptions : expenseOptions
                      }
                      placeholder="Elegir"
                    />
                    {!row.skip ? (
                      <label className="flex items-center gap-1.5 text-xs text-ink-mute">
                        <Checkbox
                          checked={row.remember !== null}
                          onCheckedChange={(checked) =>
                            change(row.number, {
                              remember:
                                checked === true
                                  ? { pattern: row.description.slice(0, 40) }
                                  : null,
                            })
                          }
                        />
                        recordar
                      </label>
                    ) : null}
                    {row.remember ? (
                      <Input
                        className="w-40 text-xs"
                        value={row.remember.pattern}
                        onChange={(event) =>
                          change(row.number, {
                            remember: { pattern: event.target.value },
                          })
                        }
                      />
                    ) : null}
                  </div>
                </td>
                <td className="tag whitespace-nowrap">
                  {ROW_STATUS_LABEL[row.status]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {missing > 0 ? (
        <p className="text-sm text-warn">
          Faltan categorías en {missing} fila{missing === 1 ? '' : 's'}.
        </p>
      ) : null}

      <ErrorText error={confirm.error} />

      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => setRows(null)}>
          Volver
        </Button>
        <Button
          disabled={missing > 0 || keeping === 0 || confirm.isPending}
          onClick={() =>
            confirm.mutate(
              {
                profile_id: profileId,
                filename,
                rows: rows.map(forConfirming),
              },
              { onSuccess: onDone },
            )
          }
        >
          {confirm.isPending ? 'Importando…' : `Importar ${keeping}`}
        </Button>
      </div>
    </div>
  );
}
