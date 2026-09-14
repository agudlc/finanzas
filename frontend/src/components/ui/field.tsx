import type { ReactNode } from 'react';

import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

/** A labelled control. The label is the uppercased one from the design system. */
export function Field({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={cn('flex flex-col gap-1.5', className)}>
      <Label className="label">{label}</Label>
      {children}
      {hint ? <span className="text-xs text-ink-mute">{hint}</span> : null}
    </label>
  );
}

export interface Option {
  value: string;
  label: string;
}

export function SelectField({
  value,
  onChange,
  options,
  placeholder = 'Elegí una opción',
  className,
}: {
  value: string | null;
  onChange: (value: string) => void;
  options: Option[];
  placeholder?: string;
  className?: string;
}) {
  return (
    <Select
      items={options}
      value={value}
      onValueChange={(next) => onChange(String(next))}
    >
      <SelectTrigger className={cn('w-full', className)}>
        {/* `items` above is what lets this render the label, not the raw value. */}
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="text-sm text-shame">
      {message}
    </p>
  );
}

export function PageTitle({ children }: { children: ReactNode }) {
  return <h1 className="display text-h1">{children}</h1>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-ink-mute">{children}</p>;
}
