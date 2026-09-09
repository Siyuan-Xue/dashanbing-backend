import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { draftTask, installSyncServer } from "../test/taskSyncFixture";
import { NewTaskPage } from "./NewTaskPage";

function open(path = "/workspace/new?draft=draft-1") {
  return render(<MemoryRouter initialEntries={[path]}><LocaleProvider><Routes><Route path="/workspace/new" element={<NewTaskPage/>}/><Route path="/workspace/tasks/:id" element={<p>任务详情</p>}/></Routes></LocaleProvider></MemoryRouter>);
}

test("task settings stay in one compact popover, persist changes and restore focus on Escape", async () => {
  const server = installSyncServer(draftTask({ sync_status: "confirmed" }));
  const user = userEvent.setup(); open();
  const trigger = await screen.findByRole("button", { name: "配置" });
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "提交分析" })).toBeEnabled();
  await user.click(trigger);
  expect(screen.getByRole("dialog", { name: "配置" })).toBeVisible();
  await user.click(screen.getByRole("radio", { name: /完整/ }));
  await user.selectOptions(screen.getByLabelText("注册方式"), "lineup");
  await user.selectOptions(screen.getByLabelText("注册人数"), "4");
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(screen.queryByRole("dialog", { name: "配置" })).not.toBeInTheDocument();
  await waitFor(() => expect(server.task).toMatchObject({ mode: "full", enrollment_mode: "lineup", expected_persons: 4 }));
  expect(screen.getByRole("button", { name: "提交分析" })).toBeEnabled();
  await user.click(trigger);
  expect(screen.getByRole("radio", { name: /完整/ })).toBeChecked();
  expect(screen.getByLabelText("注册人数")).toHaveValue("4");
  await user.click(screen.getByLabelText("任务标题"));
  expect(screen.queryByRole("dialog", { name: "配置" })).not.toBeInTheDocument();
});

test("registration fields save through draft PATCH and restore, including a single person", async () => {
  const server = installSyncServer();
  const user = userEvent.setup();
  const page = open();
  await user.click(await screen.findByRole("button", { name: "配置" }));
  expect(await screen.findByLabelText("注册方式")).toHaveValue("sequential");
  await user.selectOptions(screen.getByLabelText("注册方式"), "lineup");
  await user.selectOptions(screen.getByLabelText("注册人数"), "6");
  await waitFor(() => expect(server.task).toMatchObject({ enrollment_mode: "lineup", expected_persons: 6 }));
  expect(screen.getByRole("button", { name: "提交分析" })).toBeDisabled();
  page.unmount(); open();
  await user.click(await screen.findByRole("button", { name: "配置" }));
  expect(await screen.findByLabelText("注册方式")).toHaveValue("lineup");
  expect(screen.getByLabelText("注册人数")).toHaveValue("6");
  await user.selectOptions(screen.getByLabelText("注册人数"), "1");
  await waitFor(() => expect(server.task.expected_persons).toBe(1));
});

test("upload without opening configuration saves the manual demo defaults and keeps upload order", async () => {
  const server = installSyncServer(draftTask({ inputs: [] }));
  const user = userEvent.setup(); open("/workspace/new");
  expect(screen.getAllByLabelText(/^(注册视频|机位 [1-4])$/).map(el => el.getAttribute("aria-label"))).toEqual(["注册视频", "机位 1", "机位 2", "机位 3", "机位 4"]);
  await user.upload(screen.getByLabelText("注册视频"), new File(["video"], "players.mp4", { type: "video/mp4" }));
  expect(await screen.findByText("players.mp4")).toBeVisible();
  expect(server.writes.find(write => write.method === "POST")?.body).toMatchObject({ mode: "quick", enrollment_mode: "sequential", expected_persons: 4 });
  expect(screen.queryByRole("dialog", { name: "配置" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("任务标题")).toBeEnabled();
  expect(screen.getByRole("button", { name: "同步视频" })).toBeDisabled();
});

test("an incomplete saved draft persists the default count before submitting without opening configuration", async () => {
  const server = installSyncServer(draftTask({ mode: "full", sync_status: "confirmed" }));
  const user = userEvent.setup(); open();
  const submit = await screen.findByRole("button", { name: "提交分析" });
  expect(submit).toBeEnabled();
  await user.click(submit);
  expect(await screen.findByText("任务详情")).toBeVisible();
  expect(server.task).toMatchObject({ status: "queued", mode: "full", enrollment_mode: "sequential", expected_persons: 4 });
  const patch = server.writes.findIndex(write => write.method === "PATCH" && write.body.expected_persons === 4);
  expect(patch).toBeGreaterThanOrEqual(0);
  expect(patch).toBeLessThan(server.writes.findIndex(write => write.path.endsWith("/submit")));
});

test("existing registration choices are submitted unchanged without opening configuration", async () => {
  const server = installSyncServer(draftTask({ enrollment_mode: "lineup", expected_persons: 6, mode: "full", sync_status: "confirmed" }));
  const user = userEvent.setup(); open();
  await user.click(await screen.findByRole("button", { name: "提交分析" }));
  expect(await screen.findByText("任务详情")).toBeVisible();
  expect(server.task).toMatchObject({ status: "queued", mode: "full", enrollment_mode: "lineup", expected_persons: 6 });
  expect(server.writes.some(write => write.method === "PATCH")).toBe(false);
});

test("manual registration overrides are saved before submission", async () => {
  const server = installSyncServer(draftTask({ sync_status: "confirmed" }));
  const user = userEvent.setup(); open();
  const submit = await screen.findByRole("button", { name: "提交分析" });
  expect(submit).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "配置" }));
  await user.selectOptions(screen.getByLabelText("注册人数"), "2");
  fireEvent.change(screen.getByLabelText("任务标题"), { target: { value: "新训练" } });
  await user.click(submit);
  expect(await screen.findByText("任务详情")).toBeVisible();
  expect(server.task).toMatchObject({ status: "queued", title: "新训练", expected_persons: 2 });
});

test("camera replacement uses stale backend status while registration replacement keeps confirmation", async () => {
  installSyncServer(draftTask({ sync_status: "confirmed", expected_persons: 2 }));
  const user = userEvent.setup(); open();
  await screen.findByDisplayValue("训练草稿");
  await user.upload(screen.getByLabelText("注册视频"), new File(["video"], "players-new.mp4", { type: "video/mp4" }));
  await screen.findByText("players-new.mp4");
  expect(screen.getByRole("button", { name: "提交分析" })).toBeEnabled();
  await user.upload(screen.getByLabelText("机位 1"), new File(["video"], "camera-new.mp4", { type: "video/mp4" }));
  await screen.findByText("camera-new.mp4");
  expect(screen.getByText("视频已更换，请重新同步")).toBeVisible();
  expect(screen.getByRole("button", { name: "提交分析" })).toBeDisabled();
});

test("failed registration waits for explicit return-to-input before editing inputs", async () => {
  const server = installSyncServer(draftTask({ status: "failed", error_code: "registration_count_mismatch" }));
  const user = userEvent.setup(); open();
  await user.click(await screen.findByRole("button", { name: "修改注册输入" }));
  expect(await screen.findByLabelText("注册视频")).toBeEnabled();
  expect(server.writes.some(write => write.path.endsWith("/return-to-input"))).toBe(true);
});

test("cancel after a stale confirmation refreshes backend status instead of leaving submission enabled", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const server = installSyncServer(draftTask({ sync_status: "confirmed", expected_persons: 2 }));
  server.rejectConfirmation({ code: "sync_stale", message: "视频版本已变化" });
  const user = userEvent.setup(); open();
  await user.click(await screen.findByRole("button", { name: "同步视频" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "确认同步" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "确认同步" }));
  await screen.findByText("视频版本已变化");
  await user.click(screen.getByRole("button", { name: "取消" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "提交分析" })).toBeDisabled());
  expect(screen.getByText("视频已更换，请重新同步")).toBeVisible();
});
