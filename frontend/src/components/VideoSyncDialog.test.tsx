import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { cameras, draftTask, installSyncServer, preview, selectedTimes, versions } from "../test/taskSyncFixture";
import { VideoSyncDialog } from "./VideoSyncDialog";

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) { fireEvent.pause(this); });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async function (this: HTMLMediaElement) { fireEvent.play(this); });
});
function Host() {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  return <LocaleProvider><button onClick={() => setOpen(true)}>打开同步</button>{saved && <p>已保存同步</p>}{open && <VideoSyncDialog taskId="draft-1" onClose={() => setOpen(false)} onConfirmed={() => { setSaved(true); setOpen(false); }}/>}</LocaleProvider>;
}
async function open() {
  render(<Host/>);
  const user = userEvent.setup(); await user.click(screen.getByRole("button", { name: "打开同步" }));
  return user;
}
async function selectAll(user: ReturnType<typeof userEvent.setup>) {
  for (const camera of cameras) {
    const panel = screen.getByRole("region", { name: `机位 ${Number(camera.slice(-2))}${camera === "cam_03" ? " · 基准" : ""}` });
    await waitFor(() => expect(within(panel).getByRole("button", { name: "选定当前帧" })).toBeEnabled());
    await user.click(within(panel).getByRole("button", { name: "选定当前帧" }));
  }
}

test("starts paused, steps to actual frames, and only explicit confirmation persists version-bound timestamps", async () => {
  const server = installSyncServer(); const user = await open();
  const panel = await screen.findByRole("region", { name: "机位 1" });
  await waitFor(() => expect(within(panel).getByRole("button", { name: "下一帧" })).toBeEnabled());
  await user.click(within(panel).getByRole("button", { name: "下一帧" }));
  await waitFor(() => expect(within(panel).getByRole("slider", { name: "定位画面" })).toHaveValue("40"));
  expect(server.frames).toContainEqual({ camera: "cam_01", time: 40, version: "v1" });
  expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  await selectAll(user);
  expect(server.writes.filter(write => write.method === "PUT")).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "确认同步" }));
  expect(await screen.findByText("已保存同步")).toBeVisible();
  expect(server.writes.find(write => write.method === "PUT")?.body).toEqual({ input_versions: versions, selected_timestamps_ms: { cam_01: 40, cam_02: 0, cam_03: 0, cam_04: 0 } });
});

test("cancel and Escape discard selections, trap focus and restore the opener", async () => {
  const server = installSyncServer(); const user = await open();
  await selectAll(user);
  const confirm = screen.getByRole("button", { name: "确认同步" });
  confirm.focus(); await user.tab();
  expect(screen.getByRole("button", { name: "关闭同步" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "打开同步" })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "打开同步" }));
  await screen.findByRole("region", { name: "机位 1" });
  expect(screen.getByRole("button", { name: "确认同步" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "取消" }));
  expect(server.writes.filter(write => write.method === "PUT")).toHaveLength(0);
});

test("restores backend frame positions and linked seeking stays in common overlap", async () => {
  installSyncServer(draftTask({ sync_status: "confirmed" })); const user = await open();
  for (const camera of cameras) {
    const panel = await screen.findByRole("region", { name: `机位 ${Number(camera.slice(-2))}${camera === "cam_03" ? " · 基准" : ""}` });
    await waitFor(() => expect(within(panel).getByRole("slider", { name: "定位画面" })).toHaveValue(String(selectedTimes[camera])));
  }
  await user.click(screen.getByRole("button", { name: "联动预览" }));
  expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  const timeline = screen.getByRole("slider", { name: "共同时间" });
  expect(Number(timeline.getAttribute("max"))).toBeLessThan(280);
  fireEvent.change(timeline, { target: { value: "200" } });
  const videos = [...document.querySelectorAll("video")];
  expect(videos.map(video => Math.round(video.currentTime * 1000))).toEqual([280, 240, 200, 320]);
  await user.click(screen.getByRole("button", { name: "播放联动" }));
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(4);
});

test("stale backend confirmation is shown as an error and never reported saved", async () => {
  const server = installSyncServer(draftTask({ sync_status: "confirmed" }));
  server.rejectConfirmation({ code: "sync_stale", message: "视频版本已变化，请重新加载" });
  const user = await open();
  await waitFor(() => expect(screen.getByRole("button", { name: "确认同步" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "确认同步" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("视频版本已变化，请重新加载");
  expect(screen.queryByText("已保存同步")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "确认同步" })).toBeDisabled();
});

test("conversion preparing and failed responses never expose playable success", async () => {
  const server = installSyncServer(); server.setPreview({ ...preview, status: "preparing", cameras: {} });
  const user = await open();
  expect(await screen.findByText("正在准备同步预览…")).toBeVisible();
  expect(document.querySelector("video")).toBeNull();
  expect(screen.getByRole("button", { name: "确认同步" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "取消" }));
  server.setPreview({ ...preview, status: "failed", cameras: {}, error: { code: "preview_failed", message: "转换失败" } } as unknown as typeof preview);
  await user.click(screen.getByRole("button", { name: "打开同步" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("转换失败");
  expect(document.querySelector("video")).toBeNull();
});

test("mobile keeps cam03 visible and tabs switch one other camera with selection checks", async () => {
  vi.mocked(matchMedia).mockImplementation(query => ({ matches: true, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }) as unknown as MediaQueryList);
  installSyncServer(); const user = await open();
  await screen.findByRole("region", { name: "机位 3 · 基准" });
  expect(screen.getAllByRole("region")).toHaveLength(2);
  const panel = screen.getByRole("region", { name: "机位 1" });
  await waitFor(() => expect(within(panel).getByRole("button", { name: "选定当前帧" })).toBeEnabled());
  await user.click(within(panel).getByRole("button", { name: "选定当前帧" }));
  expect(screen.getByRole("tab", { name: "机位 1 已选定" })).toHaveAttribute("aria-selected", "true");
  await user.click(screen.getByRole("tab", { name: "机位 2" }));
  expect(screen.getByRole("region", { name: "机位 2" })).toBeVisible();
  expect(screen.queryByRole("region", { name: "机位 1" })).toBeNull();
  expect(screen.getByRole("region", { name: "机位 3 · 基准" })).toBeVisible();
});

test("linked playback rejection pauses the group and requires reloading instead of claiming success", async () => {
  installSyncServer(draftTask({ sync_status: "confirmed" })); const user = await open();
  await waitFor(() => expect(screen.getByRole("button", { name: "联动预览" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "联动预览" }));
  vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException("Unsupported source", "NotSupportedError"));
  await user.click(screen.getByRole("button", { name: "播放联动" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("视频无法播放");
  expect(screen.getByRole("button", { name: "确认同步" })).toBeDisabled();
  expect(screen.queryByText("已保存同步")).not.toBeInTheDocument();
});

test("seeking and pause capture measured frames while previous-frame selects its actual predecessor", async () => {
  const server = installSyncServer(); const user = await open();
  const panel = await screen.findByRole("region", { name: "机位 3 · 基准" });
  const seek = within(panel).getByRole("slider", { name: "定位画面" });
  fireEvent.change(seek, { target: { value: "65" } });
  await waitFor(() => expect(seek).toHaveValue("80"));
  await user.click(within(panel).getByRole("button", { name: "上一帧" }));
  await waitFor(() => expect(seek).toHaveValue("40"));
  await user.click(within(panel).getByRole("button", { name: "播放" }));
  const video = panel.querySelector("video")!; video.currentTime = .125;
  await user.click(within(panel).getByRole("button", { name: "暂停" }));
  await waitFor(() => expect(seek).toHaveValue("120"));
  await user.click(within(panel).getByRole("button", { name: "选定当前帧" }));
  expect(within(panel).getByText("0.120 s", { selector: ".video-sync-selection span" })).toBeVisible();
  expect(server.frames).toContainEqual({ camera: "cam_03", time: 120, version: "v3" });
});

test("preparing is polled until real ready metadata enables frame selection", async () => {
  const server = installSyncServer(); server.setPreview({ ...preview, status: "preparing", cameras: {} });
  await open(); await screen.findByText("正在准备同步预览…");
  server.setPreview(preview);
  const panel = await screen.findByRole("region", { name: "机位 1" }, { timeout: 2200 });
  await waitFor(() => expect(within(panel).getByRole("button", { name: "选定当前帧" })).toBeEnabled());
});
