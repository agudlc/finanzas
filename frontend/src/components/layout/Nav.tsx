import { Link } from '@tanstack/react-router';

const LINKS = [
  { to: '/', label: 'Dashboard' },
  { to: '/transacciones', label: 'Transacciones' },
  { to: '/presupuestos', label: 'Presupuestos' },
] as const;

export default function Nav() {
  return (
    <nav className="fixed bottom-5 left-1/2 -translate-x-1/2">
      <ul className="flex items-center gap-1 rounded-full border border-black/10 bg-white/80 px-2 py-2 shadow-lg backdrop-blur">
        {LINKS.map(({ to, label }) => (
          <li key={to}>
            <Link
              to={to}
              activeOptions={{ exact: to === '/' }}
              className="block rounded-full px-4 py-2 text-sm transition-colors hover:bg-black/5 [&.active]:bg-black [&.active]:text-white"
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
