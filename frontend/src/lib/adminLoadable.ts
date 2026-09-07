import { useCallback, useEffect, useState } from "react";

// Clear previous data when a query changes; stale selections must never be actionable.
export function useAdminLoadable<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [state, setState] = useState<{ value: T | null; error: unknown; loading: boolean }>({ value: null, error: null, loading: true });
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    let active = true;
    setState({ value: null, error: null, loading: true });
    loader().then(value => { if (active) setState({ value, error: null, loading: false }); }, error => { if (active) setState({ value: null, error, loading: false }); });
    return () => { active = false; };
    // The owner supplies primitive query dependencies.
  }, [revision, ...dependencies]);
  return { ...state, reload };
}
