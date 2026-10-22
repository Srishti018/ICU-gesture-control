const env = import.meta.env;
const LOCAL_NAMES = ["localhost", "127.0.0.1"];
const pageHost = typeof window !== "undefined" ? window.location.hostname : "";

// If the page was opened from another device (e.g. http://<laptop-ip>:5173),
// "localhost" would point at that device, so use the page's host instead.
function resolveHost(host) {
  if (LOCAL_NAMES.includes(host) && pageHost && !LOCAL_NAMES.includes(pageHost)) return pageHost;
  return host;
}

function resolveApiBase(base) {
  try {
    const url = new URL(base);
    url.hostname = resolveHost(url.hostname);
    return url.origin;
  } catch {
    return base;
  }
}

export const config = {
  brokerHost: resolveHost(env.VITE_BROKER_HOST || "localhost"),
  brokerWsPort: Number(env.VITE_BROKER_WS_PORT || 9001),
  username: env.VITE_DASHBOARD_USER || "dashboard",
  password: env.VITE_DASHBOARD_PASS || "",
  apiBase: resolveApiBase(env.VITE_API_BASE || "http://localhost:5050"),
};
