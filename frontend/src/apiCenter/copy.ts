export const apiCopy = {
  zh: {
    nav: "API 导航", docs: "API 文档", keys: "API 管理", toc: "本文目录", menu: "打开 API 导航", close: "关闭 API 导航",
    docsTitle: "大山冰 API 文档", docsLead: "用同一套异步任务 API 提交五路篮球训练视频，并在稍后取回状态、结果和复核媒体。",
    keysTitle: "API 管理", keysLead: "创建用于服务端集成的密钥，并查看当前账户配额。",
  },
  en: {
    nav: "API navigation", docs: "API Docs", keys: "API Management", toc: "On this page", menu: "Open API navigation", close: "Close API navigation",
    docsTitle: "DaShanBing API Docs", docsLead: "Submit five basketball training videos through one asynchronous task API, then return for status, results, and review media.",
    keysTitle: "API Management", keysLead: "Create keys for server integrations and review the current account quotas.",
  },
} as const;

export function formatRetentionDuration(locale: "zh" | "en", value: string) {
  const match = value.trim().match(/^(\d+)\s*(hours?|days?)$/i);
  if (!match) return value;
  const [, amount, rawUnit] = match;
  const unit = rawUnit.toLowerCase().startsWith("hour") ? "hour" : "day";
  if (locale === "zh") return `${amount} ${unit === "hour" ? "小时" : "天"}`;
  return `${amount} ${unit}${amount === "1" ? "" : "s"}`;
}
