import { post, request } from './request';

export interface OAuthStartBody {
  profileName?: string;
  region?: string;
  tenantId?: string;
  clientId?: string;
  clientSecret?: string;
  redirectUri?: string;
  scopes?: string;
  driveId?: string;
  siteId?: string;
  siteHostname?: string;
  sitePath?: string;
  libraryName?: string;
  rootPath?: string;
}

export interface OAuthStartResponse {
  ok: true;
  authorizationUrl: string;
  state: string;
  redirectUri: string;
  scopes: string;
}

export const oauthApi = {
  start: (body: OAuthStartBody) => post<OAuthStartResponse>('/api/oauth/start', body),
  result: (state: string) => request<{ ok: true; result: Record<string, unknown> | null }>(`/api/oauth/result/${state}`)
};
