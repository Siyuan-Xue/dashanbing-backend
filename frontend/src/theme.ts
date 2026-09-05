export type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "dashanbing-theme";

const actionTokens: Record<Theme, Record<"--brand" | "--brand-strong" | "--on-brand", string>> = {
  light: { "--brand": "#1678a6", "--brand-strong": "#126b96", "--on-brand": "#ffffff" },
  dark: { "--brand": "#73c9ed", "--brand-strong": "#9edaf1", "--on-brand": "#10232e" },
};

export function resolveInitialTheme(): Theme {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme, persist = true) {
  document.documentElement.dataset.theme = theme;
  for (const [token, value] of Object.entries(actionTokens[theme])) {
    document.documentElement.style.setProperty(token, value);
  }
  if (persist) localStorage.setItem(THEME_STORAGE_KEY, theme);
}

export function bootstrapTheme() {
  const theme = resolveInitialTheme();
  applyTheme(theme, false);
  return theme;
}
