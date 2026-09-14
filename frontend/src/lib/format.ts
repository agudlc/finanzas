/** Argentine formatting. The UI speaks Spanish and writes numbers es-AR. */

import type { BudgetState, Currency, RateType, RowStatus } from '@/lib/types';

const MONTHS = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

export const SYMBOL: Record<Currency, string> = { ARS: '$', USD: 'US$' };

export function money(amount: string | number, currency: Currency): string {
  const value = Number(amount);
  const written = new Intl.NumberFormat('es-AR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(value));
  return `${value < 0 ? '−' : ''}${SYMBOL[currency]} ${written}`;
}

/** The hero figure: no cents, and always signed, because the sign is the point. */
export function heroMoney(amount: string | number, currency: Currency): string {
  const value = Number(amount);
  const written = new Intl.NumberFormat('es-AR', {
    maximumFractionDigits: 0,
  }).format(Math.abs(value));
  return `${value < 0 ? '−' : '+'} ${SYMBOL[currency]} ${written}`;
}

/**
 * A figure typed in es-AR ("12.500,50") as the API wants it ("12500.50").
 *
 * Every amount the user types goes through here, so the thousands dots are
 * stripped in exactly one place rather than in each form that forgets to.
 */
export function decimal(typed: string): string {
  return typed.trim().replace(/\./g, '').replace(',', '.');
}

export function percent(value: string | number): string {
  return `${new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(
    Number(value),
  )}%`;
}

/** A date as the API writes it ("2026-03-15"), read without a timezone shift. */
export function parseDay(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}

export function shortDay(day: string): string {
  const date = parseDay(day);
  return `${date.getDate()} ${MONTHS[date.getMonth()].slice(0, 3)}`;
}

export function longDay(day: string): string {
  const date = parseDay(day);
  return `${date.getDate()} de ${MONTHS[date.getMonth()]} de ${date.getFullYear()}`;
}

/** A month name from either "2026-03" or a full date. */
export function monthName(month: string): string {
  const [year, number] = month.split('-').map(Number);
  return `${MONTHS[number - 1]} ${year}`;
}

export function monthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

export function shiftMonth(month: string, by: number): string {
  const [year, number] = month.split('-').map(Number);
  return monthKey(new Date(year, number - 1 + by, 1));
}

export function today(): string {
  return monthKey(new Date()) + `-${String(new Date().getDate()).padStart(2, '0')}`;
}

export const BUDGET_STATE_LABEL: Record<BudgetState, string> = {
  on_pace: 'en ritmo',
  ahead_of_pace: 'adelantado',
  warning: 'cerca del límite',
  over: 'excedido',
};

export const RATE_TYPE_LABEL: Record<RateType, string> = {
  official: 'Oficial',
  blue: 'Blue',
  mep: 'MEP',
  ccl: 'CCL',
  card: 'Tarjeta',
  manual: 'Manual',
};

export const ROW_STATUS_LABEL: Record<RowStatus, string> = {
  new: 'nueva',
  duplicate: 'duplicada',
  ignored: 'ignorada',
  needs_category: 'falta categoría',
};
