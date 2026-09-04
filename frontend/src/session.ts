type SessionExpiredListener = () => void;

const listeners = new Set<SessionExpiredListener>();

export function notifySessionExpired() {
  for (const listener of listeners) listener();
}

export function subscribeToSessionExpiry(listener: SessionExpiredListener) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
