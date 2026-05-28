import { createRootRoute } from '@tanstack/react-router';
import BaseLayout from '@/components/layout/BaseLayout';

export const Route = createRootRoute({
    component: () => BaseLayout
})