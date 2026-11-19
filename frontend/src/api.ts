export type Data = Record<string, any>;
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export const base = "/api/v1";
export async function api<T = Data>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const csrf =
    document.cookie
      .split("; ")
      .find((s) => s.startsWith("radar_csrf="))
      ?.split("=")[1] || "";
  const res = await fetch(base + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": decodeURIComponent(csrf),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      typeof e.detail === "string"
        ? e.detail
        : "Request failed (" + res.status + ")",
    );
  }
  return res.status === 204 ? ({} as T) : res.json();
}
export function url(value: unknown) {
  try {
    const u = new URL(String(value));
    return ["http:", "https:"].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
}
export const label = (s: unknown) =>
  s === null || s === undefined || s === ""
    ? "Unknown"
    : String(s).replaceAll("_", " ");
export function date(value: unknown) {
  if (!value) return "Unknown";
  const d = new Date(String(value));
  return isNaN(d.valueOf())
    ? "Unknown"
    : new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      }).format(d);
}
