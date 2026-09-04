import { Navigate, Route, Routes } from "react-router-dom";
import { RouteGuard } from "./components/RouteGuard";
import { WorkspaceShell } from "./components/WorkspaceShell";
import { AppProviders } from "./providers/AppProviders";
import { AuthPage } from "./pages/AuthPage";
import { ExampleDetailPage } from "./pages/ExampleDetailPage";
import { HomePage } from "./pages/HomePage";
import { NewTaskPage } from "./pages/NewTaskPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TaskDetailRoute } from "./pages/TaskDetailPage";
import { TaskListPage } from "./pages/TaskListPage";
import { ApiDocsPage } from "./pages/ApiDocsPage";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { ApiShell } from "./components/ApiShell";

export default function App() {
  return (
    <AppProviders>
      <Routes>
        <Route path="/" element={<HomePage/>}/>
        <Route path="/login" element={<AuthPage mode="login"/>}/>
        <Route path="/register" element={<AuthPage mode="register"/>}/>
        <Route path="/api" element={<ApiShell/>}>
          <Route index element={<Navigate to="docs" replace/>}/>
          <Route path="docs" element={<ApiDocsPage/>}/>
          <Route element={<RouteGuard/>}>
            <Route path="keys" element={<ApiKeysPage/>}/>
          </Route>
        </Route>
        <Route element={<RouteGuard/>}>
          <Route path="/workspace" element={<WorkspaceShell/>}>
            <Route index element={<Navigate to="new" replace/>}/>
            <Route path="new" element={<NewTaskPage/>}/>
            <Route path="tasks" element={<TaskListPage/>}/>
            <Route path="tasks/:taskId" element={<TaskDetailRoute/>}/>
            <Route path="examples/:presetId" element={<ExampleDetailPage/>}/>
            <Route path="settings" element={<SettingsPage/>}/>
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace/>}/>
      </Routes>
    </AppProviders>
  );
}
