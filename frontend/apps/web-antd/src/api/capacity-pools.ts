import { del, post } from './request';
import type { CapacityPool } from './dashboard';

export interface CapacityPoolSaveBody {
  id?: string;
  name: string;
}

export const capacityPoolsApi = {
  save: (body: CapacityPoolSaveBody) => post<{ ok: true; pool: CapacityPool }>('/api/capacity-pools', body),
  remove: (id: string) => del<{ ok: true }>(`/api/capacity-pools/${id}`),
};
