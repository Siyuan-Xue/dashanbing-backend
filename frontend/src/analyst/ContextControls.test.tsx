import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ContextControls } from "./ContextControls";
beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));
test("configuration switches scope and style immediately without an apply action", async () => {
  const onStyle = vi.fn(), onSubject = vi.fn(); const user = userEvent.setup();
  render(<LocaleProvider><ContextControls style="coach" subjectId="" subjects={[{ id: "s1", label: "Player 1" }]} onStyle={onStyle} onSubject={onSubject}/></LocaleProvider>);
  expect(screen.getAllByRole("combobox")).toHaveLength(2);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Analysis style"), "roast");
  expect(onStyle).toHaveBeenCalledExactlyOnceWith("roast");
  await user.selectOptions(screen.getByLabelText("View player"), "s1");
  expect(onSubject).toHaveBeenCalledExactlyOnceWith("s1");
});
