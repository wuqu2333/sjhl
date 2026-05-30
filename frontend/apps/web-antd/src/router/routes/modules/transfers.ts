import type { AdminRoute } from '../types';

export const transfersRoute: AdminRoute = {
  path: '/transfers',
  name: 'Transfers',
  component: () => import('../../../views/transfers/index.vue'),
  meta: { title: '传输', icon: 'swap', order: 30 }
};
