import { useEffect } from 'react';

export const useAutoRefresh = (fn: () => Promise<void>, intervalMs = 8000) => {
  useEffect(() => {
    fn();
    const id = setInterval(() => {
      fn();
    }, intervalMs);

    return () => clearInterval(id);
  }, [fn, intervalMs]);
};
