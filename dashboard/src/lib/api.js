import { config } from "../config.js";

const TIMEOUT_MS = 4000;

async function getJson(path) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const resp = await fetch(config.apiBase + path, { signal: controller.signal });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${path}`);
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

export const fetchAlerts = (limit = 50) => getJson(`/api/alerts?limit=${limit}`).then((d) => d.alerts);
export const fetchStats = () => getJson("/api/stats");
export const fetchHealth = () => getJson("/api/health");
