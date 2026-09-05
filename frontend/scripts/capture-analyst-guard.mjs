/** Only a real server-verified GLM report is eligible for public screenshots */
export function assertVerifiedReport(state, locale, factsHash) {
  const proof = state?.provenance; const report = state?.report;
  if (state?.status !== "completed" || proof?.provider !== "glm" || proof.verified !== true || !/^[a-f0-9]{64}$/.test(proof.facts_hash || "") || proof.facts_hash !== factsHash || !report?.id || report.model !== "glm-5.3" || report.locale !== locale || report.style !== "coach" || typeof report.summary !== "string" || !report.summary.trim() || !Array.isArray(state.facts?.evidence) || !Array.isArray(state.subjects) || !Array.isArray(report.highlights) || !Array.isArray(report.players) || !Array.isArray(report.suggestions)) {
    throw new Error("Refusing capture: a completed, verified GLM preset report matching current facts, locale and coach style is required");
  }
  const anonymous = subject => !subject.profile_id && /^(?:球员\s*|Player\s+)\d+$/.test(subject.label || "");
  if (!state.subjects.every(anonymous) || !(state.facts.subjects || []).every(anonymous) || report.comparison) throw new Error("Refusing capture: only anonymous preset subjects without profile history are eligible");
  const subjects = new Set(state.subjects.map(subject => subject.id));
  if (report.players.some(player => !subjects.has(player.subject_id))) throw new Error("Refusing capture: report player is not a known anonymous subject");
  const ids = new Set(state.facts.evidence.map(item => item.id));
  const claims = [...report.highlights, ...report.players, ...(report.comparison ? [report.comparison] : [])];
  if (claims.some(item => typeof item.text !== "string" || !Array.isArray(item.evidence_ids) || item.evidence_ids.some(id => !ids.has(id)))) throw new Error("Refusing capture: report citations do not match the current evidence");
  return report;
}

/** Native page coordinates only: never rearrange or synthesize report content */
export function captureClips({ video, report, summaryLines, textLines, rawTop }, viewport) {
  const mobile = viewport === "mobile";
  const bottom = rect => rect.y + rect.height;
  if (![video, report].every(rect => rect && Object.values(rect).every(Number.isFinite) && rect.width > 0 && rect.height > 0) || !Number.isFinite(rawTop) || bottom(video) > report.y || !summaryLines.length) throw new Error("Refusing capture: incomplete native result layout");
  const mainLimit = Math.min(video.y + (mobile ? 640 : 1040), rawTop - 8);
  const summary = [...new Set(summaryLines)].sort((a, b) => a - b).slice(0, 4);
  const mainLines = summary.filter(y => y + 4 <= mainLimit);
  if (mainLines.length < Math.min(2, summary.length)) throw new Error("Refusing capture: video and conclusion cannot fit a bounded main crop");
  const detailLimit = Math.min(report.y + (mobile ? 420 : 480), bottom(report), rawTop - 8);
  const detailLines = textLines.filter(y => y >= report.y && y + 4 <= detailLimit).sort((a, b) => a - b);
  if (!detailLines.length || detailLines.at(-1) < summary[0]) throw new Error("Refusing capture: report detail would omit the conclusion");
  const clip = (rect, end) => ({ x: Math.floor(rect.x), y: Math.floor(rect.y), width: Math.floor(rect.width), height: Math.floor(end - Math.floor(rect.y)) });
  return { main: clip(video, mainLines.at(-1) + 4), analyst: clip(report, detailLines.at(-1) + 4) };
}

export function assertCaptureMatrix(images) {
  if (images.length !== 16) throw new Error("Refusing publication: all 16 main/detail variants are required");
  const keys = new Set(); const reports = new Map();
  for (const item of images) {
    if (!["zh", "en"].includes(item.locale) || !["light", "dark"].includes(item.theme) || !["desktop", "mobile"].includes(item.viewport) || !["main", "analyst"].includes(item.kind) || item.pixel_ratio !== 2 || !Number.isInteger(item.width) || item.width <= 0 || !Number.isInteger(item.height) || item.height <= 0 || !/^[a-f0-9]{64}$/.test(item.report_hash) || !item.report_id || !/^[a-f0-9]{64}$/.test(item.facts_hash) || item.facts_hash !== images[0].facts_hash) throw new Error("Refusing publication: invalid capture variant or different session facts");
    const report = `${item.report_id}:${item.report_hash}`;
    if (reports.has(item.locale) && reports.get(item.locale) !== report) throw new Error("Refusing publication: report changed within the capture matrix");
    reports.set(item.locale, report);
    keys.add(`${item.locale}:${item.theme}:${item.viewport}:${item.kind}`);
  }
  if (keys.size !== 16) throw new Error("Refusing publication: duplicate or missing capture variant");
}
