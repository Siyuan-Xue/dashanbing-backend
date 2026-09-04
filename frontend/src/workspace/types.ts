import type { components, paths } from "../generated/schema";

export type Task =
  paths["/api/v1/tasks/{task_id}"]["get"]["responses"][200]["content"]["application/json"];
export type TaskInput = components["schemas"]["TaskInputPublic"];
export type TaskPage =
  paths["/api/v1/tasks"]["get"]["responses"][200]["content"]["application/json"];
export type Preset =
  paths["/api/v1/presets"]["get"]["responses"][200]["content"]["application/json"][number];
export type ProductResult =
  paths["/api/v1/tasks/{task_id}/result"]["get"]["responses"][200]["content"]["application/json"];
export type ProductEvent = components["schemas"]["ProductActionEvent"];
export type UsageQuota = components["schemas"]["UsageQuota"];
export type AccountUsage =
  paths["/api/v1/account/usage"]["get"]["responses"][200]["content"]["application/json"];

export type CreateTaskRequest =
  paths["/api/v1/tasks"]["post"]["requestBody"]["content"]["application/json"];
export type CreateFromPresetRequest =
  paths["/api/v1/tasks/from-preset"]["post"]["requestBody"]["content"]["application/json"];
export type TaskListQuery = NonNullable<
  paths["/api/v1/tasks"]["get"]["parameters"]["query"]
>;
export type UploadTaskPath =
  paths["/api/v1/tasks/{task_id}/inputs/{slot}"]["put"]["parameters"]["path"];
export type UploadTaskResponse =
  paths["/api/v1/tasks/{task_id}/inputs/{slot}"]["put"]["responses"][200]["content"]["application/json"];

export type TaskMode = CreateTaskRequest["mode"];
export type TaskStatus = Task["status"];
export type TaskSlot = UploadTaskPath["slot"];

export const TASK_SLOTS = [
  "enrollment_video",
  "cam_01",
  "cam_02",
  "cam_03",
  "cam_04",
] as const satisfies readonly TaskSlot[];
