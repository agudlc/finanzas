import { Link } from '@tanstack/react-router';

const LINKS = [
  { to: '/', label: 'Dashboard' },
  { to: '/transacciones', label: 'Transacciones' },
  { to: '/presupuestos', label: 'Presupuestos' },
  { to: '/ajustes', label: 'Ajustes' },
] as const;

/** The only chrome there is: a floating pill, the current page a white one. */
export default function Nav() {
  return (
    <nav className="fixed bottom-5 left-1/2 -translate-x-1/2">
      <ul className="flex items-center gap-1 rounded-pill border border-rule bg-paper-2/90 px-2 py-2 shadow-pill backdrop-blur">
        {LINKS.map(({ to, label }) => (
          <li key={to}>
            <Link
              to={to}
              activeOptions={{ exact: to === '/' }}
              className="block rounded-pill px-4 py-2 text-sm text-ink-mute transition-colors hover:text-ink [&.active]:bg-white [&.active]:text-ink [&.active]:shadow-sm"
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
