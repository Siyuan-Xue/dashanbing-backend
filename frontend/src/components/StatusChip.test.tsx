import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { StatusChip } from "./StatusChip";

describe("task cancellation presentation", () => {
  test.each(["正在取消", "Canceling"])("distinguishes %s from analysis", (stageMessage) => {
    render(<LocaleProvider><StatusChip status="running" stageMessage={stageMessage}/></LocaleProvider>);
    expect(screen.getByText("正在取消")).toBeVisible();
    expect(screen.queryByText("分析中")).not.toBeInTheDocument();
  });

  test("a stale canceling message does not override a terminal status", () => {
    render(<LocaleProvider><StatusChip status="canceled" stageMessage="正在取消"/></LocaleProvider>);
    expect(screen.getByText("已取消")).toBeVisible();
  });

  test("localizes cancellation independently of the server language", () => {
    localStorage.setItem("dashanbing-locale", "en");
    render(<LocaleProvider><StatusChip status="running" stageMessage="正在取消"/></LocaleProvider>);
    expect(screen.getByText("Canceling")).toBeVisible();
  });
});
