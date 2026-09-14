import { ChevronLeft, ChevronRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { monthName, shiftMonth } from '@/lib/format';

/** Moves one month at a time. Several of these live on screen at once. */
export default function MonthPicker({
  month,
  onChange,
  className,
}: {
  month: string;
  onChange: (month: string) => void;
  className?: string;
}) {
  return (
    <div className={`flex items-center gap-1 ${className ?? ''}`}>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Mes anterior"
        onClick={() => onChange(shiftMonth(month, -1))}
      >
        <ChevronLeft />
      </Button>
      <span className="label min-w-36 text-center">{monthName(month)}</span>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Mes siguiente"
        onClick={() => onChange(shiftMonth(month, 1))}
      >
        <ChevronRight />
      </Button>
    </div>
  );
}
