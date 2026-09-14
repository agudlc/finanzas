import { Outlet } from '@tanstack/react-router';
import Nav from '@/components/layout/Nav';

export default function BaseLayout() {
  return (
    <div className="min-h-dvh w-full overflow-x-hidden">
      <main className="flex flex-col items-center gap-5 p-5 pb-28">
        <Outlet />
      </main>
      <Nav />
    </div>
  );
}
