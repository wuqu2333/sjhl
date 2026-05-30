export async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        ...(options.body ? { 'content-type': 'application/json' } : {})
      },
      ...options
    });
  } catch (error) {
    const message = error instanceof Error && error.message !== 'Failed to fetch'
      ? error.message
      : '无法连接后端服务，请确认网络已恢复或程序仍在运行';
    throw new Error(message);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.detail || payload.error || `请求失败 ${response.status}`);
  }
  return payload as T;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function post<T = unknown>(url: string, body: Record<string, any>) {
  return request<T>(url, { method: 'POST', body: JSON.stringify(body) });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function patch<T = unknown>(url: string, body: Record<string, any>) {
  return request<T>(url, { method: 'PATCH', body: JSON.stringify(body) });
}

export function del<T = unknown>(url: string) {
  return request<T>(url, { method: 'DELETE' });
}
