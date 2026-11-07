// Thin fetch wrapper: same-origin /api (Vite proxies to FastAPI in dev), cookie session.
export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function detailMessage(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => `${(d.loc || []).slice(1).join(".") || "field"}: ${d.msg}`)
      .join("; ");
  }
  return null;
}

// Guardrail: the same write (method + path + body) fired again while the first is still in flight returns the first
// request's promise instead of sending a duplicate. Double-clicks can't create two campaigns or send two messages.
const inflight = new Map();

export function api(path, opts = {}) {
  const method = opts.method || "GET";
  if (method === "GET" || opts.form) return request(path, opts);
  const key = `${method} ${path} ${opts.body === undefined ? "" : JSON.stringify(opts.body)}`;
  if (inflight.has(key)) return inflight.get(key);
  const p = request(path, opts).finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

async function request(path, { method = "GET", body, form } = {}) {
  const opts = { method, credentials: "include", headers: {} };
  if (form) {
    opts.body = form;
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError("Can't reach the AIMVA server. Is the backend running?", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // A 5xx with no JSON detail comes from a proxy or gateway, not from the API, so the server itself is down.
    // Removed from a client's workspace: the app frame switches back to the person's own account.
    if (res.status === 403 && /access to that workspace/i.test(String(data.detail || ""))) {
      window.dispatchEvent(new CustomEvent("aimva:workspace-lost"));
    }
    const fallback = res.status >= 500 ? "Can't reach the AIMVA server. Please try again in a moment." : `Request failed (${res.status})`;
    throw new ApiError(detailMessage(data.detail) || fallback, res.status, data);
  }
  return data;
}

export const get = (p) => api(p);
export const post = (p, body) => api(p, { method: "POST", body: body ?? {} });
export const patch = (p, body) => api(p, { method: "PATCH", body });
export const put = (p, body) => api(p, { method: "PUT", body });
export const del = (p) => api(p, { method: "DELETE" });
