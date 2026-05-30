import { del, patch, post } from './request';
import type { Profile } from './dashboard';

export interface ProfileSaveBody {
  id?: string;
  name?: string;
  authMode?: string;
  region?: string;
  tenantId?: string;
  clientId?: string;
  clientSecret?: string;
  driveId?: string;
  siteId?: string;
  siteHostname?: string;
  sitePath?: string;
  libraryName?: string;
  rootPath?: string;
  capacityEnabled?: boolean;
  capacityPoolId?: string;
}

export const profilesApi = {
  save: (body: ProfileSaveBody) => post<{ ok: true; profile: Profile }>('/api/profiles', body),
  setCapacityEnabled: (id: string, capacityEnabled: boolean) =>
    patch<{ ok: true; profile: Profile }>(`/api/profiles/${id}/capacity`, { capacityEnabled }),
  setCapacityPool: (id: string, capacityPoolId: string) =>
    patch<{ ok: true; profile: Profile }>(`/api/profiles/${id}/capacity-pool`, { capacityPoolId }),
  remove: (id: string) => del(`/api/profiles/${id}`)
};
