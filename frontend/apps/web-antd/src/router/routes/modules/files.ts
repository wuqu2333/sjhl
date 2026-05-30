import type { AdminRoute } from '../types';

export const filesRoute: AdminRoute = {
  path: '/files',
  name: 'Files',
  component: () => import('../../../views/files/index.vue'),
  meta: { title: '文件', icon: 'folder', order: 20 }
};
