import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { applyTheme, bootstrapTheme } from "../theme";
import type { Theme } from "../theme";

type ThemeContextValue = { theme: Theme; setTheme: (theme: Theme) => void; toggleTheme: () => void };
const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const existing = document.documentElement.dataset.theme;
    if (existing === "light" || existing === "dark") return existing;
    return bootstrapTheme();
  });
  useEffect(() => applyTheme(theme), [theme]);
  const value = useMemo(() => ({ theme, setTheme, toggleTheme: () => setTheme((current) => current === "dark" ? "light" : "dark") }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
