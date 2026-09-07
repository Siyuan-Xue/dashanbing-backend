import { AdminAuditPage } from "./AdminAuditPage";
import { AdminOperationsPage } from "./AdminOperationsPage";
import { AdminOverviewPage } from "./AdminOverviewPage";
import { AdminQuotasPage } from "./AdminQuotasPage";
import { AdminSchedulingPage } from "./AdminSchedulingPage";
import { AdminUsersPage } from "./AdminUsersPage";
export type AdminSection = "overview" | "users" | "scheduling" | "quotas" | "operations" | "audit";
const sections = { overview: AdminOverviewPage, users: AdminUsersPage, scheduling: AdminSchedulingPage, quotas: AdminQuotasPage, operations: AdminOperationsPage, audit: AdminAuditPage };
export function AdminPage({ section }: { section: AdminSection }) { const Page = sections[section]; return <Page/>; }
