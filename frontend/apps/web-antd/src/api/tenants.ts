import { del, post } from './request';
import type { Profile, TenantConnection } from './dashboard';

export interface TenantSaveBody {
  id?: string;
  name?: string;
  authMode?: string;
  region?: string;
  tenantId?: string;
  clientId?: string;
  clientSecret?: string;
  refreshToken?: string;
  defaultRootPath?: string;
  importDocumentsOnly?: boolean;
}

export interface TenantDiscoverBody {
  search?: string;
  documentsOnly?: boolean;
}

export interface TenantMountBody {
  siteUrl?: string;
  libraryName?: string;
  rootPath?: string;
  documentsOnly?: boolean;
}

export interface DiscoverDrive {
  siteId: string;
  siteName: string;
  siteWebUrl: string;
  driveId: string;
  driveName: string;
  driveType: string;
  webUrl: string;
  quotaTotal: number;
  quotaUsed: number;
  quotaRemaining: number;
  quotaState: string;
}

export interface ImportResult {
  ok: true;
  count: number;
  profiles: Profile[];
}

export interface MountResult {
  ok: true;
  count: number;
  site: Record<string, unknown>;
  drives: DiscoverDrive[];
  profiles: Profile[];
}

export const tenantsApi = {
  save: (body: TenantSaveBody) => post<{ ok: true; connection: TenantConnection }>('/api/tenant-connections', body),
  discover: (id: string, body: TenantDiscoverBody = {}) =>
    post<{ ok: true; drives: DiscoverDrive[] }>(`/api/tenant-connections/${id}/discover`, body),
  import: (id: string, body: TenantDiscoverBody = {}) =>
    post<ImportResult>(`/api/tenant-connections/${id}/import`, body),
  mountSharePoint: (id: string, body: TenantMountBody) =>
    post<MountResult>(`/api/tenant-connections/${id}/mount-sharepoint`, body),
  remove: (id: string) => del(`/api/tenant-connections/${id}`)
};
