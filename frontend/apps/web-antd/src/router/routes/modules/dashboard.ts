import type { AdminRoute } from '../types';

export const dashboardRoute: AdminRoute = {
  path: '/',
  name: 'Dashboard',
  component: () => import('../../../views/dashboard/index.vue'),
  meta: { title: '工作台', icon: 'dashboard', order: 10 }
};
