import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { HeroAnalystPreview } from "./HeroAnalystPreview";

test.each(["zh", "en"])("renders a localized static illustration without fetching reports or screenshots: %s", locale => {
  localStorage.setItem("dashanbing-locale", locale);
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const { container } = render(<MemoryRouter><LocaleProvider><HeroAnalystPreview/></LocaleProvider></MemoryRouter>);
  expect(screen.getByRole("img", { name: locale === "zh" ? /AI 分析师功能示意/ : /AI analyst illustration/ })).toBeVisible();
  expect([...container.querySelectorAll(".ai-preview-stats b")].map(element => element.textContent)).toEqual(["4", "2", "50%"]);
  expect(container.querySelectorAll(".ai-preview-cameras img")).toHaveLength(2);
  expect(screen.getByRole("link", { name: locale === "zh" ? "查看 AI 复盘" : "View AI review" })).toHaveAttribute("href", "/workspace/examples/quick-demo#analyst");
  expect(fetch).not.toHaveBeenCalled();
  expect(container.querySelector("button, input, select, textarea")).toBeNull();
});

test("decorative illustration does not create an interactive preview", () => {
  render(<MemoryRouter><LocaleProvider><HeroAnalystPreview decorative/></LocaleProvider></MemoryRouter>);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
