import { ReactNode } from "react";
import { AuthProvider } from "./AuthProvider";
import { LocaleProvider } from "./LocaleProvider";
import { ThemeProvider } from "./ThemeProvider";

export function AppProviders({ children }: { children: ReactNode }) {
  return <ThemeProvider><LocaleProvider><AuthProvider>{children}</AuthProvider></LocaleProvider></ThemeProvider>;
}
