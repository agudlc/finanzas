import { Empty } from '@/components/ui/field';
import TransactionRow from '@/components/transactions/TransactionRow';
import type { Category, Transaction } from '@/lib/types';

export default function TransactionList({
  transactions,
  categories,
  empty = 'Todavía no hay movimientos.',
}: {
  transactions: Transaction[];
  categories: Category[];
  empty?: string;
}) {
  if (transactions.length === 0) return <Empty>{empty}</Empty>;
  const byId = new Map(categories.map((category) => [category.id, category]));
  return (
    <ul className="w-full">
      {transactions.map((transaction) => (
        <TransactionRow
          key={transaction.id}
          transaction={transaction}
          category={byId.get(transaction.category_id)}
        />
      ))}
    </ul>
  );
}
