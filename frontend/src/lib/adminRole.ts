import type { AuthUser } from "../api";

// Keep the role boundary local while the parent refreshes the generated contract.
export type RoleUser = AuthUser & { role?: "admin" | "user" };
export const isAdmin = (user: RoleUser | null) => user?.role === "admin";
export const accountHome = (user: RoleUser | null) => isAdmin(user) ? "/admin" : "/workspace/new";
export function loginDestination(user: RoleUser, next: string) {
  if (isAdmin(user)) return "/admin";
  return next === "/admin" || next.startsWith("/admin/") || next.startsWith("/admin?") ? "/workspace/new" : next;
}
