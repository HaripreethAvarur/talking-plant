/** The viewer token for a token-protected backend, set at runtime in sessionStorage. */
export function viewerToken(): string | null {
  try {
    return sessionStorage.getItem("plantViewerToken");
  } catch {
    return null;
  }
}

/** fetch() against the backend, with the viewer token and JSON handling. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = viewerToken();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...init, headers });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return body as T;
}
