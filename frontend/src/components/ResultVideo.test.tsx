import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ResultVideo } from "./ResultVideo";

test("applies a pending evidence seek when metadata arrives and preserves muted autoplay", () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  render(<LocaleProvider><ResultVideo src="/cam2.mp4" title="Camera 2" seek={{ id: 1, seconds: 23.5 }}/></LocaleProvider>);
  const video = screen.getByTitle("Camera 2") as HTMLVideoElement;
  expect(video.currentTime).toBe(0);
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(23.5);
  expect(video.muted).toBe(true);
  expect(video.defaultMuted).toBe(true);
  expect(video).toHaveAttribute("autoplay");
  fireEvent.canPlay(video);
  expect(play).toHaveBeenCalledOnce();
  video.currentTime = 24;
  fireEvent.canPlay(video);
  expect(video.currentTime).toBe(24);
});

test("seeks immediately after metadata and handles repeat clicks at the same timestamp", () => {
  const view = (id: number) => <LocaleProvider><ResultVideo src="/cam2.mp4" title="Camera 2" seek={{ id, seconds: 8 }}/></LocaleProvider>;
  const rendered = render(view(1));
  const video = screen.getByTitle("Camera 2") as HTMLVideoElement;
  Object.defineProperty(video, "readyState", { value: 1, configurable: true });
  fireEvent.loadedMetadata(video);
  video.currentTime = 30;
  rendered.rerender(view(2));
  expect(video.currentTime).toBe(8);
});
