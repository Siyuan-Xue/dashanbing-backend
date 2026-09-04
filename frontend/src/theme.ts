export type Theme = "light" | "dark";

const THEME_STORAGE_KEY = "dashanbing-theme";

const actionTokens: Record<Theme, Record<"--brand" | "--brand-strong" | "--on-brand", string>> = {
  light: { "--brand": "#5361ff", "--brand-strong": "#3f4bd8", "--on-brand": "#ffffff" },
  dark: { "--brand": "#7d85ff", "--brand-strong": "#979dff", "--on-brand": "#101326" },
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
