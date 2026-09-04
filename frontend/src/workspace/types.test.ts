import { expectTypeOf, test } from "vitest";

import type { components, paths } from "../generated/schema";
import type {
  AccountUsage,
  CreateFromPresetRequest,
  CreateTaskRequest,
  Preset,
  ProductEvent,
  ProductResult,
  Task,
  TaskInput,
  TaskListQuery,
  TaskMode,
  TaskPage,
  TaskSlot,
  TaskStatus,
  UploadTaskPath,
  UsageQuota,
} from "./types";

test("workspace models and request contracts come directly from generated OpenAPI types", () => {
  expectTypeOf<Task>().toEqualTypeOf<components["schemas"]["TaskPublic"]>();
  expectTypeOf<TaskInput>().toEqualTypeOf<components["schemas"]["TaskInputPublic"]>();
  expectTypeOf<TaskPage>().toEqualTypeOf<components["schemas"]["TaskListPublic"]>();
  expectTypeOf<Preset>().toEqualTypeOf<components["schemas"]["PresetPublic"]>();
  expectTypeOf<ProductEvent>().toEqualTypeOf<components["schemas"]["ProductActionEvent"]>();
  expectTypeOf<ProductResult>().toEqualTypeOf<components["schemas"]["ProductResult"]>();
  expectTypeOf<UsageQuota>().toEqualTypeOf<components["schemas"]["UsageQuota"]>();
  expectTypeOf<AccountUsage>().toEqualTypeOf<components["schemas"]["AccountUsage"]>();

  expectTypeOf<TaskMode>().toEqualTypeOf<components["schemas"]["TaskCreate"]["mode"]>();
  expectTypeOf<TaskStatus>().toEqualTypeOf<components["schemas"]["TaskPublic"]["status"]>();
  expectTypeOf<TaskSlot>().toEqualTypeOf<
    paths["/api/v1/tasks/{task_id}/inputs/{slot}"]["put"]["parameters"]["path"]["slot"]
  >();
  expectTypeOf<CreateTaskRequest>().toEqualTypeOf<
    paths["/api/v1/tasks"]["post"]["requestBody"]["content"]["application/json"]
  >();
  expectTypeOf<CreateFromPresetRequest>().toEqualTypeOf<
    paths["/api/v1/tasks/from-preset"]["post"]["requestBody"]["content"]["application/json"]
  >();
  expectTypeOf<TaskListQuery>().toEqualTypeOf<
    NonNullable<paths["/api/v1/tasks"]["get"]["parameters"]["query"]>
  >();
  expectTypeOf<UploadTaskPath>().toEqualTypeOf<
    paths["/api/v1/tasks/{task_id}/inputs/{slot}"]["put"]["parameters"]["path"]
  >();
});
