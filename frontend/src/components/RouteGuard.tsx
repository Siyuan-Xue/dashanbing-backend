import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";

export function RouteGuard() {
  const { checking, user } = useAuth();
  const location = useLocation();
  if (checking) return <div className="route-loading" role="status"><span/></div>;
  if (!user) {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?${new URLSearchParams({ next })}`} replace />;
  }
  return <Outlet />;
}
