export const TASK_SLOTS = ["enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04"] as const;
export type TaskSlot = typeof TASK_SLOTS[number];
export type TaskMode = "quick" | "full";
export type TaskStatus = "draft" | "uploading" | "queued" | "running" | "completed" | "failed" | "canceled" | "expired";

export type TaskInput = {
  slot: TaskSlot;
  original_filename: string;
  byte_size: number;
  validation_state: string;
  created_at: string;
  updated_at: string;
};
export type Task = {
  id: string;
  title: string;
  mode: TaskMode;
  source_type: string;
  preset_id: string | null;
  status: TaskStatus;
  progress: number;
  stage_message: string;
  error_code: string | null;
  error_message: string | null;
  submitted_at: string | null;
  created_via: string;
  retry_count: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  inputs: TaskInput[];
};

export type TaskPage = { items: Task[]; total: number; page: number; page_size: number };
export type Preset = { id: string; title: string; description: string; expected_minutes: number };

export type ProductEvent = {
  event_index: number;
  action_type: "triple_threat" | "free_throw" | "jump_shot" | "layup";
  start_ms: number;
  end_ms: number;
  time_ms: number;
  result: "make" | "miss" | "undetermined" | null;
};

export type ProductResult = {
  registered_participant_count: number;
  action_counts: Record<"triple_threat" | "free_throw" | "jump_shot" | "layup", number>;
  unsupported_event_count: number;
  shots: { attempts: number; makes: number; misses: number; undetermined: number; make_rate: number | null; unlinked_outcomes: number };
  events: ProductEvent[];
  media: Partial<Record<"phases" | "cam_01" | "cam_02" | "cam_03" | "cam_04", string>>;
  warnings: string[];
  disclaimer: string;
};

export type UsageQuota = { used: number; limit: number };
export type AccountUsage = {
  submitted_today: UsageQuota;
  unfinished_tasks: UsageQuota;
  drafts: UsageQuota;
  active_api_keys: UsageQuota;
  retention: { drafts: string; enrollment_data: string; raw_inputs: string; results: string };
};
