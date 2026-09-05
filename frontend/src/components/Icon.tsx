type IconName = "logout" | "collapse" | "expand" | "copy" | "download" | "chevronLeft" | "chevronDown" | "chevronRight" | "filter" | "arrow" | "basketball" | "chart" | "check" | "clock" | "code" | "file" | "github" | "language" | "layers" | "menu" | "moon" | "plus" | "play" | "refresh" | "search" | "settings" | "sun" | "trash" | "upload" | "user" | "x";

const paths: Record<IconName, React.ReactNode> = {
  logout: <><path d="M9 4H4v16h5M9 12h12m-4-4 4 4-4 4"/></>,
  collapse: <path d="m11 6-6 6 6 6m7-12-6 6 6 6"/>,
  expand: <path d="m6 6 6 6-6 6m7-12 6 6-6 6"/>,
  copy: <><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/></>,
  download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></>,
  chevronDown: <path d="m6 9 6 6 6-6"/>,
  chevronLeft: <path d="m15 5-7 7 7 7"/>,
  chevronRight: <path d="m9 5 7 7-7 7"/>,
  filter: <path d="M3 4h18v3l-7 5v8l-4-2v-6L3 7V4Z"/>,
  arrow: <><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></>,
  basketball: <><circle cx="12" cy="12" r="9"/><path d="M3.6 9.2c5.2.2 9.7 4.4 10 9.7M8.5 4.7c4.8 3.6 7.2 8.2 7 14.1M4.2 15.7c4.5-3.5 9.6-5.1 15.5-4.7"/></>,
  chart: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V3"/><path d="M2 19h21"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></>,
  code: <><path d="m8 9-3 3 3 3M16 9l3 3-3 3M14 5l-4 14"/></>,
  file: <><path d="M6 2h8l4 4v16H6Z"/><path d="M14 2v5h5"/></>,
  github: <path d="M12 2.8a9.3 9.3 0 0 0-2.9 18.1c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 0 1.6 1 1.6 1 .9 1.6 2.4 1.1 3 .9.1-.7.4-1.1.7-1.4-2.3-.3-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7-.1-.3-.5-1.3.1-2.7 0 0 .9-.3 2.8 1a9.6 9.6 0 0 1 5.1 0c2-1.3 2.8-1 2.8-1 .6 1.4.2 2.4.1 2.7.7.7 1 1.6 1 2.7 0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.8v2.7c0 .4.2.6.7.5A9.3 9.3 0 0 0 12 2.8Z"/>,
  language: <><circle cx="12" cy="12" r="9"/><path d="M3.5 12h17M12 3c2.5 2.5 3.8 5.5 3.8 9S14.5 18.5 12 21C9.5 18.5 8.2 15.5 8.2 12S9.5 5.5 12 3Z"/></>,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  moon: <path d="M20 15.2A8.4 8.4 0 0 1 8.8 4 8.8 8.8 0 1 0 20 15.2Z"/>,
  plus: <path d="M12 5v14M5 12h14"/>,
  play: <path d="m9 7 8 5-8 5V7Z"/>,
  refresh: <><path d="M20 7v5h-5"/><path d="M18.2 17.8a8 8 0 1 1 1.5-8.6L20 12"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
  sun: <><circle cx="12" cy="12" r="3.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
  trash: <><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/></>,
  upload: <><path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 14v6h16v-6"/></>,
  user: <><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/></>,
  x: <path d="m6 6 12 12M18 6 6 18"/>,
};

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg aria-hidden="true" className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}
