/** The one place the app talks to the backend. */

const BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  'http://localhost:8000/api/v1';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** The backend answers a broken rule with `detail`; validation with a list. */
async function messageOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((problem: { msg?: string }) => problem.msg ?? '')
        .filter(Boolean)
        .join('. ');
    }
  } catch {
    /* an empty or non-JSON body leaves only the status */
  }
  return `La petición falló (${response.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init);
  if (!response.ok) throw new ApiError(response.status, await messageOf(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function withJson(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, withJson('POST', body)),
  patch: <T>(path: string, body: unknown) => request<T>(path, withJson('PATCH', body)),
  put: <T>(path: string, body: unknown) => request<T>(path, withJson('PUT', body)),
  remove: (path: string) => request<void>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),
};

export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const asText = search.toString();
  return asText ? `?${asText}` : '';
}
