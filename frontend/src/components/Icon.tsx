import {
  Activity, ArrowRight, Ban, CalendarX, ChartColumn, Check, ChevronDown,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, CircleAlert,
  CircleDot, Clock, Code, Copy, Download, File, Funnel, Globe, Layers,
  LogOut, Menu, MessageCircle, Minus, Moon, Pencil, Play, Plus, RefreshCw,
  Search, Settings, Sparkles, Square, Sun, Trash2, Upload, User, Users, X,
  type LucideIcon,
} from "lucide-react";
import "../styles/ai-showcase.css";

export type IconName = "sparkles" | "chat" | "team" | "pencil" | "activity" | "stop" | "statusCheck" | "alert" | "ban" | "calendarX" | "logout" | "collapse" | "expand" | "copy" | "download" | "chevronLeft" | "chevronDown" | "chevronRight" | "filter" | "arrow" | "basketball" | "chart" | "check" | "clock" | "code" | "file" | "github" | "language" | "layers" | "menu" | "moon" | "plus" | "play" | "refresh" | "search" | "settings" | "sun" | "trash" | "upload" | "user" | "x" | "minus";

// Preserve the public names used throughout the workspace. Lucide has no
// basketball icon; CircleDot is its neutral ball-like symbol. Brands use assets.
const icons: Record<Exclude<IconName, "github">, LucideIcon> = {
  sparkles: Sparkles, chat: MessageCircle, team: Users, pencil: Pencil,
  activity: Activity, stop: Square, statusCheck: Check, alert: CircleAlert,
  ban: Ban, calendarX: CalendarX, logout: LogOut, collapse: ChevronsLeft,
  expand: ChevronsRight, copy: Copy, download: Download, chevronLeft: ChevronLeft,
  chevronDown: ChevronDown, chevronRight: ChevronRight, filter: Funnel,
  arrow: ArrowRight, basketball: CircleDot, chart: ChartColumn, check: Check,
  clock: Clock, code: Code, file: File, language: Globe, layers: Layers,
  menu: Menu, moon: Moon, plus: Plus, minus: Minus, play: Play, refresh: RefreshCw,
  search: Search, settings: Settings, sun: Sun, trash: Trash2, upload: Upload,
  user: User, x: X,
};

export function Icon({ name, size = 20, spin = false, className = "" }: { name: IconName; size?: number; spin?: boolean; className?: string }) {
  if (name === "github") return <span aria-hidden="true" className={`icon icon-github ${className}`.trim()} style={{ width: size, height: size }}>
    <img className="github-mark-light" src="/assets/brand/github-invertocat-black.svg" width={size} height={size} alt=""/>
    <img className="github-mark-dark" src="/assets/brand/github-invertocat-white.svg" width={size} height={size} alt=""/>
  </span>;
  const Component = icons[name];
  // Inline stroke/fill isolates official UI icons from legacy brand fill rules.
  return <Component aria-hidden="true" focusable="false" className={`icon${spin ? " icon-spin" : ""} ${className}`.trim()} size={size} strokeWidth={1.8} style={{ fill: "none", stroke: "currentColor" }}/>;
}
