import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/transacciones')({
  component: Transacciones,
});

function Transacciones() {
  return <h1 className="text-2xl">Transacciones</h1>;
}
