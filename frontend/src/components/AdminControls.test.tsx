import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { AdminConfirm } from "./AdminConfirm";
import { AdminMetadataDrawer } from "./AdminMetadataDrawer";

beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));
test("confirmation requires a meaningful reason and acknowledgement before sending a mutation", async () => {
  const sent: string[] = [];
  const user = userEvent.setup();
  render(<LocaleProvider><AdminConfirm title="Hold jobs" targets={["job-1"]} onClose={() => undefined} onConfirm={async reason => { sent.push(reason); }}/></LocaleProvider>);
  const confirm = screen.getByRole("button", { name: "Confirm action" });
  expect(confirm).toBeDisabled();
  await user.type(screen.getByRole("textbox", { name: "Reason" }), "  maintenance  ");
  expect(confirm).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(confirm);
  expect(sent).toEqual(["maintenance"]);
});
test("failed mutation keeps the confirmation and does not show success", async () => {
  const user = userEvent.setup();
  render(<LocaleProvider><AdminConfirm title="Hold jobs" targets={["job-1"]} onClose={() => undefined} onConfirm={async () => { throw new Error("internal secret"); }}/></LocaleProvider>);
  await user.type(screen.getByRole("textbox", { name: "Reason" }), "maintenance");
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "Confirm action" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The action did not complete");
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(screen.queryByText("internal secret")).not.toBeInTheDocument();
  expect(screen.queryByText("Action completed")).not.toBeInTheDocument();
});
test("metadata drawer renders only explicitly supplied display fields and restores focus", async () => {
  const user = userEvent.setup();
  let closed = false;
  render(<LocaleProvider><AdminMetadataDrawer title="Job metadata" fields={[["Task ID", "job-1"], ["Status", "Queued"]]} onClose={() => { closed = true; }}/></LocaleProvider>);
  expect(screen.getByRole("dialog", { name: "Job metadata" })).toHaveTextContent("job-1");
  await user.keyboard("{Escape}");
  expect(closed).toBe(true);
});
