let csrf = "";
export function setCSRF(value: string) {
  csrf = value;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET")
    headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Please check the form fields",
    );
  }
  return response.json();
}
