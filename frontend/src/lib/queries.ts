/**
 * Server state, through TanStack Query.
 *
 * Everything the screens read and write goes through here, so a mutation knows
 * exactly which reads it made stale.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';

import { api, query } from '@/lib/api';
import type {
  BudgetProgress,
  CategorizationRule,
  Category,
  FileColumns,
  ImportPreview,
  ImportProfile,
  ImportRecord,
  InstallmentPurchase,
  MonthlySpending,
  MonthlySummary,
  Settings,
  Transaction,
} from '@/lib/types';

export const keys = {
  categories: ['categories'] as const,
  settings: ['settings'] as const,
  transactions: (params: Record<string, string | number | undefined> = {}) =>
    ['transactions', params] as const,
  budgets: (month?: string) => ['budgets', month ?? 'current'] as const,
  summary: (month?: string) => ['summary', month ?? 'current'] as const,
  spending: (month?: string) => ['spending', month ?? 'current'] as const,
  purchases: ['installment-purchases'] as const,
  profiles: ['import-profiles'] as const,
  rules: ['categorization-rules'] as const,
  imports: ['imports'] as const,
};

/** Anything that changes money makes all of these stale. */
const MONEY = [
  ['transactions'],
  ['budgets'],
  ['summary'],
  ['spending'],
  ['installment-purchases'],
  ['imports'],
];

function invalidate(client: QueryClient, keysToDrop: readonly string[][]) {
  for (const key of keysToDrop) {
    void client.invalidateQueries({ queryKey: key });
  }
}

/**
 * A mutation that says what it makes stale.
 *
 * Every write in this file is this shape, so the only thing worth stating per
 * mutation is which reads it invalidates.
 */
function useWrite<Input, Output>(
  run: (input: Input) => Promise<Output>,
  stale: readonly string[][] = MONEY,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => invalidate(client, stale),
  });
}

const CATEGORIES = [[...keys.categories], ...MONEY];
const PROFILES = [[...keys.profiles]];
const RULES = [[...keys.rules]];
const SETTINGS = [[...keys.settings], ...MONEY];

export function useCategories() {
  return useQuery({
    queryKey: keys.categories,
    queryFn: () => api.get<Category[]>('/categories/'),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<Settings>('/settings/'),
  });
}

export function useUpdateSettings() {
  return useWrite(
    (changes: Partial<Settings>) => api.patch<Settings>('/settings/', changes),
    SETTINGS,
  );
}

export function useTransactions(
  params: Record<string, string | number | undefined> = {},
) {
  return useQuery({
    queryKey: keys.transactions(params),
    queryFn: () => api.get<Transaction[]>(`/transactions/${query(params)}`),
  });
}

export function useSummary(month?: string) {
  return useQuery({
    queryKey: keys.summary(month),
    queryFn: () => api.get<MonthlySummary>(`/summary/${query({ month })}`),
  });
}

export function useSpending(month?: string) {
  return useQuery({
    queryKey: keys.spending(month),
    queryFn: () =>
      api.get<MonthlySpending>(`/summary/by-category${query({ month })}`),
  });
}

export function useBudgets(month?: string) {
  return useQuery({
    queryKey: keys.budgets(month),
    queryFn: () => api.get<BudgetProgress[]>(`/budgets/${query({ month })}`),
  });
}

export function useCreateTransaction() {
  return useWrite((body: Record<string, unknown>) =>
    api.post<Transaction>('/transactions/', body),
  );
}

export function useUpdateTransaction() {
  return useWrite(
    ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      api.patch<Transaction>(`/transactions/${id}`, changes),
  );
}

export function useDeleteTransaction() {
  return useWrite((id: string) => api.remove(`/transactions/${id}`));
}

export function useCreateRefund() {
  return useWrite(
    ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.post<Transaction>(`/transactions/${id}/refund`, body),
  );
}

export function usePurchases() {
  return useQuery({
    queryKey: keys.purchases,
    queryFn: () => api.get<InstallmentPurchase[]>('/installment-purchases/'),
  });
}

export function useCreatePurchase() {
  return useWrite((body: Record<string, unknown>) =>
    api.post<InstallmentPurchase>('/installment-purchases/', body),
  );
}

export function useDeletePurchase() {
  return useWrite((id: string) =>
    api.remove(`/installment-purchases/${id}`),
  );
}

export function useCreateBudget() {
  return useWrite((body: Record<string, unknown>) =>
    api.post<BudgetProgress>('/budgets/', body),
  );
}

export function useUpdateBudget() {
  return useWrite(
    ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      api.patch<BudgetProgress>(`/budgets/${id}`, changes),
  );
}

export function useDeleteBudget() {
  return useWrite((id: string) => api.remove(`/budgets/${id}`));
}

export function useCreateCategory() {
  return useWrite(
    (body: Record<string, unknown>) => api.post<Category>('/categories/', body),
    CATEGORIES,
  );
}

export function useUpdateCategory() {
  return useWrite(
    ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      api.patch<Category>(`/categories/${id}`, changes),
    CATEGORIES,
  );
}

export function useDeleteCategory() {
  return useWrite((id: string) => api.remove(`/categories/${id}`), CATEGORIES);
}

export function useProfiles() {
  return useQuery({
    queryKey: keys.profiles,
    queryFn: () => api.get<ImportProfile[]>('/import-profiles/'),
  });
}

export function useCreateProfile() {
  return useWrite(
    (body: Record<string, unknown>) =>
      api.post<ImportProfile>('/import-profiles/', body),
    PROFILES,
  );
}

export function useUpdateProfile() {
  return useWrite(
    ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      api.patch<ImportProfile>(`/import-profiles/${id}`, changes),
    PROFILES,
  );
}

export function useDeleteProfile() {
  return useWrite(
    (id: string) => api.remove(`/import-profiles/${id}`),
    PROFILES,
  );
}

/** The column headings of an export, so a Profile is written from a real file. */
export function useReadColumns() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.set('file', file);
      return api.upload<FileColumns>('/import-profiles/columns', form);
    },
  });
}

export function useRules() {
  return useQuery({
    queryKey: keys.rules,
    queryFn: () => api.get<CategorizationRule[]>('/categorization-rules/'),
  });
}

export function useUpdateRule() {
  return useWrite(
    ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      api.patch<CategorizationRule>(`/categorization-rules/${id}`, changes),
    RULES,
  );
}

export function useDeleteRule() {
  return useWrite(
    (id: string) => api.remove(`/categorization-rules/${id}`),
    RULES,
  );
}

export function useImports() {
  return useQuery({
    queryKey: keys.imports,
    queryFn: () => api.get<ImportRecord[]>('/imports/'),
  });
}

export function usePreviewImport() {
  return useMutation({
    mutationFn: ({ profileId, file }: { profileId: string; file: File }) => {
      const form = new FormData();
      form.set('profile_id', profileId);
      form.set('file', file);
      return api.upload<ImportPreview>('/imports/preview', form);
    },
  });
}

export function useConfirmImport() {
  return useWrite(
    (body: Record<string, unknown>) => api.post<ImportRecord>('/imports/', body),
    // A confirm can also create "remember" Categorization Rules.
    [...MONEY, ...RULES],
  );
}

export function useUndoImport() {
  return useWrite((id: string) => api.remove(`/imports/${id}`));
}
