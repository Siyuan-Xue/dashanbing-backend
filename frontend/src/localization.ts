import type { Locale } from "./copy";

const DISCLAIMER_ZH = "AI 识别结果，仅供训练复盘。";
const DISCLAIMER_EN = "AI-generated results are for training review only.";

export function formatRetentionDuration(locale: Locale, value: string) {
  const match = value.trim().match(/^(\d+)\s*(hours?|days?)$/i);
  if (!match) return value;
  const [, amount, rawUnit] = match;
  const unit = rawUnit.toLowerCase().startsWith("hour") ? "hour" : "day";
  if (locale === "zh") return `${amount} ${unit === "hour" ? "小时" : "天"}`;
  return `${amount} ${unit}${amount === "1" ? "" : "s"}`;
}

export function localizeResultMessage(locale: Locale, value: string) {
  if (value === DISCLAIMER_ZH || value === DISCLAIMER_EN) {
    return locale === "zh" ? DISCLAIMER_ZH : DISCLAIMER_EN;
  }

  const unsupported = /^(\d+) 个事件属于当前版本未支持的动作类型。$/.exec(value);
  if (unsupported) {
    if (locale === "zh") return value;
    const count = unsupported[1];
    return `${count} ${count === "1" ? "event uses" : "events use"} action types not supported by this version.`;
  }

  const unlinked = /^(\d+) 个投篮结果无法可靠关联到最终动作片段。$/.exec(value);
  if (unlinked) {
    if (locale === "zh") return value;
    const count = unlinked[1];
    return `${count} shot ${count === "1" ? "result" : "results"} could not be reliably linked to a final action clip.`;
  }

  return value;
}
