import { Navigate, Route, Routes } from "react-router-dom";
import { RouteGuard } from "./components/RouteGuard";
import { AppProviders } from "./providers/AppProviders";
import { AuthPage } from "./pages/AuthPage";
import { HomePage } from "./pages/HomePage";
import { ProtectedRouteScaffold } from "./pages/ProtectedRouteScaffold";

export default function App() {
  return (
    <AppProviders>
      <Routes>
        <Route path="/" element={<HomePage/>}/>
        <Route path="/login" element={<AuthPage mode="login"/>}/>
        <Route path="/register" element={<AuthPage mode="register"/>}/>
        <Route element={<RouteGuard/>}>
          <Route path="/workspace/*" element={<ProtectedRouteScaffold/>}/>
          <Route path="/api/keys" element={<ProtectedRouteScaffold/>}/>
        </Route>
        <Route path="*" element={<Navigate to="/" replace/>}/>
      </Routes>
    </AppProviders>
  );
}
