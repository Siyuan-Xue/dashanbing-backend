import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Icon, type IconName } from "./Icon";

const legacyNames: IconName[] = ["sparkles", "chat", "team", "pencil", "activity", "stop", "statusCheck", "alert", "ban", "calendarX", "logout", "collapse", "expand", "copy", "download", "chevronLeft", "chevronDown", "chevronRight", "filter", "arrow", "basketball", "chart", "check", "clock", "code", "file", "language", "layers", "menu", "moon", "plus", "play", "refresh", "search", "settings", "sun", "trash", "upload", "user", "x"];

test("all existing UI icon names render official Lucide icons at the requested size", () => {
  const { container } = render(<>{legacyNames.map(name => <Icon key={name} name={name} size={18}/>)}</>);
  expect(container.querySelectorAll("svg.lucide")).toHaveLength(legacyNames.length);
  for (const icon of container.querySelectorAll("svg")) {
    expect(icon).toHaveAttribute("width", "18");
    expect(icon).toHaveAttribute("height", "18");
    expect(icon).toHaveAttribute("stroke-width", "1.8");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  }
});

test("refresh uses RefreshCw without altering the accessible button name", () => {
  render(<button aria-label="Refresh report"><Icon name="refresh"/></button>);
  expect(screen.getByRole("button", { name: "Refresh report" }).querySelector(".lucide-refresh-cw")).not.toBeNull();
});

test("GitHub loads a static official brand asset outside the UI SVG styling", () => {
  const { container } = render(<a href="https://github.com" aria-label="GitHub"><Icon name="github" size={16}/></a>);
  expect(screen.getByRole("link", { name: "GitHub" })).toBeVisible();
  expect(container.querySelector("svg")).toBeNull();
  expect(container.querySelector("img")).toHaveAttribute("src", "/assets/brand/github-invertocat-black.svg");
  expect(container.querySelector("img")).toHaveAttribute("alt", "");
});


test("supports caller animation classes and the shared spin option", () => {
  const { container } = render(<Icon name="refresh" className="report-refreshing" spin/>);
  expect(container.querySelector("svg")).toHaveClass("lucide-refresh-cw", "report-refreshing", "icon-spin");
});
