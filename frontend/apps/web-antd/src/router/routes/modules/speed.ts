import type { AdminRoute } from '../types';
import SpeedView from '../../../views/speed/index.vue';

export const speedRoute: AdminRoute = {
  path: '/speed',
  name: 'Speed',
  component: SpeedView,
  meta: { title: '速度监控', icon: 'thunderbolt', order: 25, shortTitle: '速度' }
};
