import { useCallback, useEffect, useState } from "react";

export const THEME_KEY = "icu-dashboard-theme";

/** Stored choice, else the OS preference, else dark (the laptop default). */
export function initialTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Storage blocked (private window, file://): fall through to the OS preference.
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function useTheme() {
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(THEME_KEY, next);
      } catch {
        // Not persisted; the toggle still works for this page.
      }
      return next;
    });
  }, []);

  return { theme, toggle };
}
