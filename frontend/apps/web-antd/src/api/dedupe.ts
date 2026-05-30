import { del, post, request } from './request';

export interface DuplicateGroup {
  key: string;
  count: number;
  ids: string;
  files: string;
  profiles: string;
  paths: string;
  items: string;
  urls: string;
  algorithm: string;
  hash: string;
  size: number;
}

export const dedupeApi = {
  clear: () => del('/api/dedupe'),
  duplicates: () => request<{ ok: true; groups: DuplicateGroup[] }>('/api/dedupe/duplicates'),
  deleteFile: (profileId: string, itemId: string) =>
    post('/api/dedupe/delete-file', { profile_id: profileId, item_id: itemId }),
};
