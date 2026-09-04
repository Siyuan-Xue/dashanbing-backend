import { Navigate, Route, Routes } from "react-router-dom";
import { RouteGuard } from "./components/RouteGuard";
import { WorkspaceShell } from "./components/WorkspaceShell";
import { AppProviders } from "./providers/AppProviders";
import { AuthPage } from "./pages/AuthPage";
import { ExampleDetailPage } from "./pages/ExampleDetailPage";
import { HomePage } from "./pages/HomePage";
import { NewTaskPage } from "./pages/NewTaskPage";
import { ProtectedRouteScaffold } from "./pages/ProtectedRouteScaffold";
import { SettingsPage } from "./pages/SettingsPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { TaskListPage } from "./pages/TaskListPage";

export default function App() {
  return (
    <AppProviders>
      <Routes>
        <Route path="/" element={<HomePage/>}/>
        <Route path="/login" element={<AuthPage mode="login"/>}/>
        <Route path="/register" element={<AuthPage mode="register"/>}/>
        <Route element={<RouteGuard/>}>
          <Route path="/workspace" element={<WorkspaceShell/>}>
            <Route index element={<Navigate to="new" replace/>}/>
            <Route path="new" element={<NewTaskPage/>}/>
            <Route path="tasks" element={<TaskListPage/>}/>
            <Route path="tasks/:taskId" element={<TaskDetailPage/>}/>
            <Route path="examples/:presetId" element={<ExampleDetailPage/>}/>
            <Route path="settings" element={<SettingsPage/>}/>
          </Route>
          <Route path="/api/keys" element={<ProtectedRouteScaffold/>}/>
        </Route>
        <Route path="*" element={<Navigate to="/" replace/>}/>
      </Routes>
    </AppProviders>
  );
}
