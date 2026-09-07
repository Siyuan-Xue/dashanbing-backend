import type { AdminOverview, AdminTimingKey } from "../lib/adminApi";
import { useAdminCopy, type AdminCopyKey } from "../lib/adminCopy";
import { AdminTable, useAdminFormat } from "./AdminShared";

const timings: [AdminTimingKey, AdminCopyKey][] = [
  ["video_queue_seconds", "videoQueueTime"],
  ["video_execution_seconds", "videoExecutionTime"],
  ["ai_total_seconds", "aiTotalTime"],
];

const errorLabels: Record<string, AdminCopyKey> = {
  engine_failed: "engineFailed", registration_count_mismatch: "registrationCountMismatch",
  registration_quality_failed: "registrationQualityFailed", registration_config_required: "registrationConfigRequired",
  interrupted: "interrupted", preparation_failed: "preparationFailed", generation_failed: "generationFailed", unknown: "unknown",
};

export function AdminPerformanceSummary({ timings: values, errors }: Pick<AdminOverview, "timings" | "errors">) {
  const t = useAdminCopy();
  const format = useAdminFormat();
  const metric = (value: number | null | undefined) => value == null ? t("telemetryUnavailable") : format.number(value);
  return <div className="admin-performance-summary">
    <section><h2>{t("timingSummary")}</h2><p className="admin-hint">{t("timingScope")}</p>
      <AdminTable label={t("timingSummary")} headings={[t("kind"), t("sampleCount"), "P50", "P95"]}>
        {timings.map(([key, label]) => <tr key={key}><td>{t(label)}</td><td>{metric(values?.[key]?.count)}</td><td>{metric(values?.[key]?.p50)}</td><td>{metric(values?.[key]?.p95)}</td></tr>)}
      </AdminTable>
    </section>
    <section><h2>{t("errorCategories")}</h2><p className="admin-hint">{t("errorScope")}</p>
      {errors?.length ? <AdminTable label={t("errorCategories")} headings={[t("kind"), t("errorCode"), t("errorCount")] }>
        {errors.map((error, index) => <tr key={`${error.kind}:${error.code}:${index}`}><td>{t(error.kind)}</td><td>{t(errorLabels[error.code] || "unknown")}<small><code>{errorLabels[error.code] ? error.code : "unknown"}</code></small></td><td>{format.number(error.count)}</td></tr>)}
      </AdminTable> : <div className="admin-summary-empty" role="region" aria-label={t("errorCategories")}><p>{t(errors ? "noRecordedErrors" : "telemetryUnavailable")}</p></div>}
    </section>
  </div>;
}
