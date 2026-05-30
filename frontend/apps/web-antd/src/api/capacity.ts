import { post } from './request';

export const capacityApi = {
  refreshAll: () => post<{ ok: true; refreshed: number; results: Array<Record<string, unknown>> }>('/api/capacity/refresh-all', {})
};
