import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import type { Locale } from "../copy";
import { apiHeadings, headingFromHash } from "./chapters";
import type { ApiHeadingId } from "./chapters";

const headingOffset = () => (document.querySelector(".public-header")?.getBoundingClientRect().height || 76) + 21;
const alignHeading = (target: HTMLElement) => window.scrollTo({ top: Math.max(0, window.scrollY + target.getBoundingClientRect().top - headingOffset()), behavior: "instant" });

export function useDocsNavigation(locale: Locale, expanded: boolean, compact: boolean) {
  const location = useLocation();
  const [active, setActive] = useState<ApiHeadingId>(() => headingFromHash(location.hash)?.id ?? "overview");
  const tocRef = useRef<HTMLElement>(null);
  const previousLocale = useRef(locale);

  useLayoutEffect(() => {
    if (previousLocale.current === locale) return;
    previousLocale.current = locale;
    if (window.scrollY === 0) return;
    // Translation changes layout, but must preserve both the reading chapter and focus.
    const target = document.getElementById(active);
    if (target) alignHeading(target);
  }, [active, locale]);

  useLayoutEffect(() => {
    const heading = headingFromHash(location.hash);
    if (!heading) return;
    const target = document.getElementById(heading.id);
    if (!target) return;
    setActive(heading.id);
    // Immediate alignment also respects reduced motion and browser history restoration.
    target.focus({ preventScroll: true });
    alignHeading(target);
  }, [location.hash, location.key]);

  useEffect(() => {
    let frame = 0;
    const track = () => {
      frame = 0;
      const offset = headingOffset() + 1;
      let current: ApiHeadingId = "overview";
      for (const heading of apiHeadings) {
        const element = document.getElementById(heading.id);
        if (element && element.getBoundingClientRect().top <= offset) current = heading.id;
        else break;
      }
      if (window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) current = "errors";
      setActive(current);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(track); };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);

  useLayoutEffect(() => {
    const nav = tocRef.current;
    const link = nav?.querySelector<HTMLElement>('[aria-current="location"]');
    if (!nav || !link || (compact && !expanded)) return;
    const viewport = nav.getBoundingClientRect();
    const item = link.getBoundingClientRect();
    // Scroll only the TOC, never the article, when its active entry is out of view.
    if (item.top < viewport.top) nav.scrollTop -= viewport.top - item.top;
    else if (item.bottom > viewport.bottom) nav.scrollTop += item.bottom - viewport.bottom;
  }, [active, compact, expanded, locale]);

  return { active, tocRef };
}
