import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON } from "./api.js";

/** Poll a URL every `ms` while `active`. */
export function usePoll(path, ms, active) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);
  const tick = useCallback(async () => {
    if (!path) return;
    try {
      setData(await getJSON(path));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [path]);
  useEffect(() => {
    if (!path) { setData(null); return undefined; }
    tick();
    if (!active) return undefined;
    timer.current = setInterval(tick, ms);
    return () => clearInterval(timer.current);
  }, [path, ms, active, tick]);
  return { data, error, refresh: tick, setData };
}

export function useBackendStatus() {
  const health = usePoll("/health", 20000, true);
  const chain = usePoll("/chain", 15000, true);
  return { health: health.data, chain: chain.data, offline: !!health.error, refreshChain: chain.refresh };
}
