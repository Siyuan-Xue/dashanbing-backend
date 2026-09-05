import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { AppProviders } from "../providers/AppProviders";
import { previewFixture } from "../test/analystPreviewFixture";
import { HomePage } from "./HomePage";

function renderHome() {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => String(input).includes("/assets/previews/")
    ? Response.json(previewFixture()) : Response.json({ detail: "Not authenticated" }, { status: 401 })));
  return render(<MemoryRouter><AppProviders><HomePage/></AppProviders></MemoryRouter>);
}

test("preserves the basketball hero and places the standalone AI showcase before capabilities", async () => {
  const { container } = renderHome();
  const title = screen.getByRole("heading", { level: 1, name: "让我看看你打球什么b样" });
  const hero = title.closest("section")!;
  expect(within(hero).getByAltText("实际模型输出：四机位篮球画面、人物骨架、球框与跳投阶段标注")).toHaveAttribute("src", "/assets/previews/quick-phases.webp");
  expect(within(hero).getAllByRole("link")).toHaveLength(2);
  const showcase = screen.getByRole("region", { name: "AI 分析师，看懂这一场，练好下一场" });
  expect(hero.nextElementSibling).toBe(showcase);
  expect(showcase.nextElementSibling).toHaveClass("capabilities-section");
  expect(await within(showcase).findByAltText("同场训练报告局部")).toBeVisible();
  expect(showcase.querySelectorAll("picture")).toHaveLength(1);
  expect(within(showcase).getByRole("link", { name: "查看 AI 复盘" })).toHaveAttribute("href", "/workspace/examples/quick-demo#analyst");
  expect(container.querySelectorAll(".product-preview-metrics b")).toHaveLength(4);
  // Cross-checked against local sample-bundle group_04 report.json and summary.json.
  expect([...container.querySelectorAll(".product-preview-metrics b")].map(node => node.textContent)).toEqual(["4", "2", "4", "4"]);
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
});

test("mobile menu and capability controls keep accessible labels with official icons", async () => {
  renderHome();
  const menu = screen.getByRole("button", { name: "打开导航菜单" });
  expect(menu.querySelector(".lucide-menu")).not.toBeNull();
  fireEvent.click(menu);
  expect(screen.getByRole("button", { name: "关闭导航菜单" }).querySelector(".lucide-x")).not.toBeNull();
  const cards = screen.getAllByTestId("capability-card");
  const next = within(cards[1]).getByRole("button");
  expect(next.querySelector(".lucide-plus")).not.toBeNull();
  fireEvent.click(next);
  expect(next).toHaveAttribute("aria-expanded", "true");
  expect(next.querySelector(".lucide-minus")).not.toBeNull();
  await screen.findByAltText("同场训练报告局部");
});
