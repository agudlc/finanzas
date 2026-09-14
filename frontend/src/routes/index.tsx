import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/')({
  component: Dashboard,
});

function Dashboard() {
  return <h1 className="text-2xl">Dashboard</h1>;
}
