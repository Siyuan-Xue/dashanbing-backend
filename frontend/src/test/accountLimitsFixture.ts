import type { AccountLimits } from "../apiCenter/api";

// Account overrides deliberately differ from server defaults.
export const accountLimitsFixture: AccountLimits = {
  quotas: { drafts: 3, unfinished: 5, daily_video: 20, daily_ai: 37 },
  application: {
    max_upload_size_gb: 4, draft_ttl_hours: 24,
    enrollment_retention_days: 7, raw_retention_days: 30, result_retention_days: 180,
    analyst_daily_limit: 100,
  },
};
