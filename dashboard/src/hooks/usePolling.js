import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Call fetchFn now and every intervalMs. Returns {data, error, refresh}.
 * On failure the last good data is kept and error is set.
 */
export function usePolling(fetchFn, intervalMs) {
  const [state, setState] = useState({ data: null, error: null });
  const fnRef = useRef(fetchFn);
  fnRef.current = fetchFn;

  const refresh = useCallback(async () => {
    try {
      const data = await fnRef.current();
      setState({ data, error: null });
    } catch (error) {
      setState((s) => ({ data: s.data, error }));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { ...state, refresh };
}
