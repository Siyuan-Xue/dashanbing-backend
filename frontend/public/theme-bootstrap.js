try {
  const storedTheme = localStorage.getItem("dashanbing-theme");
  document.documentElement.dataset.theme = storedTheme === "light" || storedTheme === "dark"
    ? storedTheme
    : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
} catch {
  document.documentElement.dataset.theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
