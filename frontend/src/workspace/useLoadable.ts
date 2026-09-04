import { useCallback, useEffect, useState } from "react";

export function useLoadable<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((current) => current + 1), []);
  useEffect(() => {
    let active = true;
    setError(null);
    loader().then((result) => { if (active) setValue(result); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason : new Error("Request failed")); });
    return () => { active = false; };
    // The caller supplies stable primitive dependencies for each request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revision, ...dependencies]);
  return { value, error, reload, loading: value === null && error === null };
}
