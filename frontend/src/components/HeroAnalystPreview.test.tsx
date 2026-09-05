import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ThemeProvider } from "../providers/ThemeProvider";
import { previewFixture } from "../test/analystPreviewFixture";
import { HeroAnalystPreview } from "./HeroAnalystPreview";

test("without verified screenshots the showcase uses the actual basketball frame and truthful unavailable state", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("No manifest")));
  render(<MemoryRouter><LocaleProvider><ThemeProvider><HeroAnalystPreview/></ThemeProvider></LocaleProvider></MemoryRouter>);
  expect(await screen.findByText("示例截图暂不可用")).toBeVisible();
  expect(screen.getByAltText("真实篮球训练画面")).toHaveAttribute("src", "/assets/previews/quick-cam-1.webp");
  expect(screen.getByRole("link", { name: "查看 AI 复盘" })).toHaveAttribute("href", "/workspace/examples/quick-demo#analyst");
  expect(screen.queryByText("00:06 / 00:48")).not.toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.every(([url]) => String(url) === "/assets/previews/analyst/manifest.json")).toBe(true);
});

test("loads verified static screenshot sources and falls back if a shipped asset fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(previewFixture())));
  render(<MemoryRouter><LocaleProvider><ThemeProvider><HeroAnalystPreview/></ThemeProvider></LocaleProvider></MemoryRouter>);
  const image = await screen.findByAltText("同场训练报告局部");
  expect(image).toHaveAttribute("srcset", "/assets/previews/analyst/zh-light-desktop-analyst.webp 1440w");
  expect(image.closest("picture")?.querySelector("source")).toHaveAttribute("srcset", "/assets/previews/analyst/zh-light-mobile-analyst.webp 708w");
  expect(screen.queryByAltText("真实示例的 AI 分析师界面")).not.toBeInTheDocument();
  fireEvent.error(image);
  expect(screen.getByText("示例截图暂不可用")).toBeVisible();
});

test.each(["zh", "en"].flatMap(locale => ["light", "dark"].map(theme => ({ locale, theme }))))("selects the native report crop for $locale/$theme in desktop and mobile sources", async ({ locale, theme }) => {
  localStorage.setItem("dashanbing-locale", locale); localStorage.setItem("dashanbing-theme", theme);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(previewFixture())));
  const { container } = render(<MemoryRouter><LocaleProvider><ThemeProvider><HeroAnalystPreview/></ThemeProvider></LocaleProvider></MemoryRouter>);
  await screen.findByAltText(locale === "zh" ? "同场训练报告局部" : "Report detail from the same session");
  for (const kind of ["analyst"]) {
    const image = container.querySelector(`img[src$="${locale}-${theme}-desktop-${kind}.webp"]`);
    expect(image).not.toBeNull();
    expect(image?.closest("picture")?.querySelector("source")?.getAttribute("srcset")).toContain(`${locale}-${theme}-mobile-${kind}.webp`);
  }
});
