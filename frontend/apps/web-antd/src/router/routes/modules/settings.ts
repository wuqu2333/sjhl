import type { AdminRoute } from '../types';

export const settingsRoute: AdminRoute = {
  path: '/settings',
  name: 'Settings',
  component: () => import('../../../views/settings/index.vue'),
  meta: { title: '设置', icon: 'cluster', order: 40 }
};
