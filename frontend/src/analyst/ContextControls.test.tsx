import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ContextControls } from "./ContextControls";

beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));
test("configuration only changes style when applied, with no history or binding selector", async () => {
  const apply = vi.fn(), close = vi.fn(); const user = userEvent.setup();
  render(<LocaleProvider><ContextControls style="coach" open onApply={apply} onClose={close}/></LocaleProvider>);
  expect(screen.getAllByRole("combobox")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Apply and update analysis" })).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Analysis style"), "roast");
  expect(apply).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Apply and update analysis" }));
  expect(apply).toHaveBeenCalledExactlyOnceWith("roast");
  expect(close).toHaveBeenCalledOnce();
});
test("closing and reopening discards uncommitted configuration", async () => {
  const apply = vi.fn(); const user = userEvent.setup();
  const ui = (open:boolean) => <LocaleProvider><ContextControls style="coach" open={open} onApply={apply} onClose={() => {}}/></LocaleProvider>;
  const view = render(ui(true));
  await user.selectOptions(screen.getByLabelText("Analysis style"), "roast");
  view.rerender(ui(false)); view.rerender(ui(true));
  expect(screen.getByLabelText("Analysis style")).toHaveValue("coach");
  expect(apply).not.toHaveBeenCalled();
});
