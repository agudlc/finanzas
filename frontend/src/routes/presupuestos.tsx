import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/presupuestos')({
  component: Presupuestos,
});

function Presupuestos() {
  return <h1 className="text-2xl">Presupuestos</h1>;
}
