import { del, post, request } from './request';

export interface Pan115Item {
  fid: string;
  cid: string;
  name: string;
  size: number;
  isDir: boolean;
  pickCode: string;
  sha1: string;
  mtime: string;
}

export interface Pan115Account {
  id: string;
  name: string;
  hasCookie: boolean;
  hasAccessToken: boolean;
}

export const pan115Api = {
  listDir: (accountId: string, cid = '0') =>
    post<{ ok: true; cid: string; items: Pan115Item[] }>('/api/pan115/list-dir', { accountId, cid }),
  listAccounts: () => request<{ ok: true; accounts: Pan115Account[] }>('/api/pan115/accounts'),
  saveAccount: (body: Record<string, unknown>) => post('/api/pan115/accounts', body),
  removeAccount: (id: string) => del(`/api/pan115/accounts/${id}`),
  clouddriveAutoAuth: (accountId: string) =>
    post<{ ok: true; accessToken: string; refreshToken: string }>('/api/pan115/open/clouddrive/auto-auth', { accountId }),
  userInfo: (accountId: string) =>
    post<{ ok: true; info: any }>('/api/pan115/user-info', { accountId }),
  searchFiles: (accountId: string, keyword: string, cid = '') =>
    post<{ ok: true; items: any[] }>('/api/pan115/search', { accountId, keyword, cid }),
  deleteFiles: (accountId: string, fileIds: string[], parentId = '0') =>
    post('/api/pan115/delete-files', { accountId, fileIds, parentId }),
  createFolder: (accountId: string, pid: string, name: string) =>
    post<{ ok: true; folder: any }>('/api/pan115/create-folder', { accountId, pid, name }),
};
