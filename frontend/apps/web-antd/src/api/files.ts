import { del, post, request } from './request';

export interface DriveFileItem {
  id: string;
  driveId?: string;
  name: string;
  path: string;
  type: 'folder' | 'file';
  size: number;
  childCount: number;
  mimeType: string;
  lastModifiedDateTime: string;
  webUrl: string;
  downloadUrl: string;
}

export const filesApi = {
  children: (profileId: string, path = '') =>
    request<{ ok: true; profile: Record<string, any>; path: string; items: DriveFileItem[] }>(
      `/api/files/${encodeURIComponent(profileId)}/children?path=${encodeURIComponent(path)}`
    ),
  createFolder: (profileId: string, body: { path: string; name: string; conflictBehavior?: string }) =>
    post(`/api/files/${encodeURIComponent(profileId)}/folders`, body),
  deleteItem: (profileId: string, itemId: string, driveId = '', path = '', itemType = 'file') =>
    del(
      `/api/files/${encodeURIComponent(profileId)}/items/${encodeURIComponent(itemId)}?${
        [
          driveId ? `driveId=${encodeURIComponent(driveId)}` : '',
          path ? `path=${encodeURIComponent(path)}` : '',
          itemType ? `itemType=${encodeURIComponent(itemType)}` : ''
        ].filter(Boolean).join('&')
      }`
    ),
  renameItem: (profileId: string, itemId: string, name: string, driveId = '') =>
    request<{ ok: true }>(
      `/api/files/${encodeURIComponent(profileId)}/items/${encodeURIComponent(itemId)}${
        driveId ? `?driveId=${encodeURIComponent(driveId)}` : ''
      }`,
      {
      method: 'PATCH', body: JSON.stringify({ name })
      }
    ),
  search: (profileId: string, query: string) =>
    request<{ ok: true; items: any[] }>(`/api/files/${encodeURIComponent(profileId)}/search?q=${encodeURIComponent(query)}`),
  upload: async (profileId: string, path: string, file: File) => {
    const response = await fetch(
      `/api/files/${encodeURIComponent(profileId)}/upload?path=${encodeURIComponent(path)}&fileName=${encodeURIComponent(
        file.name
      )}&size=${file.size}&conflictBehavior=rename`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/octet-stream' },
        body: file
      }
    );
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.detail || payload.error || `上传失败 ${response.status}`);
    }
    return payload;
  }
};
