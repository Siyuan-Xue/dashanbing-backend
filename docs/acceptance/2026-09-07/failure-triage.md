# 最终集中测试失败只读归因

日期：2026-09-07，工作树 `codex/ai-analyst`。本报告只读取指定验收产物及相关源码/契约，未改代码、测试或断言，未执行任何重复验收、补跑、优化或修复。下面的“通过”只引用已有产物，不代表本次重新验证。未访问凭据文件、真实用户数据或生产系统；不抄录账户、令牌、私有响应正文或完整 DOM。

**25 项后端失败不能改写为通过。现有证据支持：13 项旧契约断言，12 项夹具不兼容导致目标行为未验证，0 项已被这些记录证实的新契约下产品缺陷。“0 项已证实”不等于“没有缺陷”。最高关注的是 8 项撤销竞争场景未执行到关键时点，涉及已撤销结果重新发布和配额账本保留；另有 3 项产品流水线产物、1 项预置生成 CLI 的目标未验证。**

## 原始结果与口径

| 产物 | 原始结果 | 证据 |
| --- | --- | --- |
| 后端 pytest/JUnit | 842 项，817 通过、25 失败、0 error、0 skipped；74.80 秒 | [JUnit 汇总](raw/backend-tests.xml)；[失败清单与统计](raw/backend-tests.log) |
| 前端 Playwright | 242 项，177 expected、4 unexpected、61 skipped、0 flaky；JSON duration 94118.301 ms | [stats](raw/frontend-e2e.json)；[日志统计](raw/frontend-e2e.log) |
| 前端 Vitest | 263 项，262 通过、1 失败、0 pending；success=false | [完整 JSON](raw/frontend-unit.json)，字段 `numTotalTests/numFailedTests/testResults` |

Vitest 同时报告 `numFailedTestSuites=2`，但 `testResults` 中只有一个失败文件和一个失败断言；不能据此虚构第二个失败用例，suite 层级计数的具体口径未验证。Playwright 的 61 项 skipped 不是通过；本报告不将 Chromium 项目结果外推到原生 Safari 或实体 iPhone。

分类说明：

- **旧契约**：失败差异可由明确的新契约和实现解释，保留失败原样；发生失败之后的断言依然没有执行
- **未验证**：夹具/注入点在目标行为之前阻断，不能以“测试过时”为由声称目标安全或功能可用
- **真实缺陷**：须有证据显示实现违反当前契约；本批失败尚未提供足以定性的实例，测试夹具适配问题本身仍是实际测试维护问题

## 后端 25 项逐项清单

每行保留一个独立的原始失败节点，参数化用例分别列出。R 编号对应后面的根因及风险说明。

| 编号 | 失败节点及断言源码 | 已观察到的失败 | 分类 / 根因 | 原始证据 |
| --- | --- | --- | --- | --- |
| B01 | [test_analyst_collections.py::test_collection_queues_full_reports_for_both_styles_once_and_charges_once](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_collections.py#L36) | 202 ≠ 429 | 旧契约 / R1 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B02 | [test_analyst_comparisons.py::test_comparison_validation_dedup_and_quota_are_separate_from_session[coach]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_comparisons.py#L224) | 202 ≠ 429 | 旧契约 / R1 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B03 | [test_analyst_comparisons.py::test_comparison_validation_dedup_and_quota_are_separate_from_session[roast]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_comparisons.py#L224) | 202 ≠ 429 | 旧契约 / R1 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B04 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[profile_edit-False-report]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 等待 provider 开始超时 | 未验证 / R2 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B05 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[profile_edit-False-message]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 超时；领取任务缺共享 runtime | 未验证 / R3 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B06 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[profile_edit-True-report]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 等待 provider 开始超时 | 未验证 / R2 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B07 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[profile_edit-True-message]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 超时；领取任务缺共享 runtime | 未验证 / R3 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B08 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[task_delete-False-report]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 等待 provider 开始超时 | 未验证 / R2 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B09 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[task_delete-False-message]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 超时；领取任务缺共享 runtime | 未验证 / R3 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B10 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[task_delete-True-report]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 等待 provider 开始超时 | 未验证 / R2 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B11 | [test_analyst_invalidation.py::test_scoped_inflight_revocation_cannot_republish_or_release_quota[task_delete-True-message]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L461) | 超时；领取任务缺共享 runtime | 未验证 / R3 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B12 | [test_analyst_jobs.py::test_invalidation_between_claim_and_load_cannot_delete_ledger_or_restart_message[before_load-report]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_jobs.py#L816) | attempts 0 ≠ 1 | 旧契约 / R4 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B13 | [test_analyst_jobs.py::test_invalidation_between_claim_and_load_cannot_delete_ledger_or_restart_message[before_load-message]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_jobs.py#L816) | attempts 0 ≠ 1 | 旧契约 / R4 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B14 | [test_analyst_jobs.py::test_invalidation_between_claim_and_load_cannot_delete_ledger_or_restart_message[after_load-report]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_jobs.py#L816) | attempts 0 ≠ 1 | 旧契约 / R4 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B15 | [test_analyst_jobs.py::test_invalidation_between_claim_and_load_cannot_delete_ledger_or_restart_message[after_load-message]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_jobs.py#L816) | attempts 0 ≠ 1 | 旧契约 / R4 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B16 | [test_analyst_pose.py::test_product_real_runner_carries_task_context_and_retains_artifact[0.5-True]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_pose.py#L314) | registration_quality_failed | 未验证 / R5 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B17 | [test_analyst_pose.py::test_product_real_runner_carries_task_context_and_retains_artifact[30.0-False]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_pose.py#L314) | registration_quality_failed | 未验证 / R5 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B18 | [test_analyst_pose.py::test_product_real_runner_carries_task_context_and_retains_artifact[52.0-False]](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_pose.py#L314) | registration_quality_failed | 未验证 / R5 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B19 | [test_analyst_report_regressions.py::test_generator_reuses_legacy_preset_and_fills_both_styles](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_report_regressions.py#L149) | 旧 GlmClient 替换入口不存在 | 未验证 / R6 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B20 | [test_analyst_report_regressions.py::test_additive_migration_defaults_language_and_preserves_legacy_rows](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_report_regressions.py#L245) | 任务字典多 3 个新增字段 | 旧契约 / R7 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B21 | [test_app.py::test_readiness_rejects_admin_password_that_does_not_match_database](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_app.py#L165) | readyz 200 ≠ 503 | 旧契约 / R8 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B22 | [test_app.py::test_registration_normalizes_identity_and_returns_a_public_user](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_app.py#L240) | 响应多 role=user | 旧契约 / R9 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B23 | [test_presets.py::test_preset_rerun_manifest_binds_registration_cameras_and_group_sync](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_presets.py#L114) | manifest 多 2 个注册字段 | 旧契约 / R10 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B24 | [test_readiness.py::test_real_readiness_names_missing_active_models_and_sync](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_readiness.py#L55) | 缺少旧全局 sync_config 检查项 | 旧契约 / R10 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |
| B25 | [test_tasks_api.py::test_submit_requires_all_slots_and_injects_sync_only_at_submit](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_tasks_api.py#L547) | 任务同步快照 ≠ 旧全局 offset 字典 | 旧契约 / R10 | [log](raw/backend-tests.log) · [XML](raw/backend-tests.xml) |

## 根因与实际风险

### R1：3 项 AI 限额断言仍修改启动后的 AppSettings

B01 将 `analyst_daily_limit` 改为 1，B02/B03 改为 2；实际配置已经在启动时持久化，后续准入读取默认/个人配额，而不是被修改的设置对象。源码分别见 [旧设置变更](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_collections.py#L19)、[比较测试旧设置变更](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_comparisons.py#L210)、[启动持久化](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin.py#L24)、[持久化配置与个人覆盖](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin.py#L45)、[准入检查](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/analyst.py#L67)。该夹具原始每日限额为 100，见 [应用创建前设置](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_jobs.py#L103)。

因此 202 并不能证明管理员设置的有效限额被绕过。当前同一 XML 已记录 `test_personal_quota_changes_new_admission_only` 和 `test_manual_daily_quota_covers_regeneration_and_chat_but_excludes_automatic_and_duplicates` 通过（[管理员配额记录](raw/backend-tests.xml)、[手动操作配额记录](raw/backend-tests.xml)）。这些旁证不使 B01–B03 通过，也不补足比较测试在第 224 行之后的生成、再生成和不重复计费断言。

### R2：4 项 report 撤销竞争测试的报告目标仍为 completed

B04/B06/B08/B10 只把 job 改回 queued，却没有把它指向的报告从 completed 改回待生成状态。目标报告由 [seed_analyst_work](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_training_profiles.py#L218) 建立为 completed；[测试仅重置 job](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L441) 保留了该状态。新领取逻辑在 [成功目标保护](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin_scheduling.py#L244) 遇到 completed 输出时将 job 标记失败并跳过，故 provider 不会触发 started，最终只见等待超时。

这是从夹具与领取条件推导的直接原因，日志未记录逐条数据库轨迹，不能称为额外动态验证。它没有证明运行中的报告被错误丢弃，也没有验证之后的 profile_edit/task_delete 与迟到结果竞争。**这 4 项的“不重新发布已撤销结果、隔离无关任务、保留账本”仍未验证。**

### R3：4 项 message 撤销竞争测试缺少共享运行目录绑定

B05/B07/B09/B11 的原始异常明确为 `Shared runtime is required for worker claims`，不是 provider 业务超时。夹具用裸 `FastAPI()` 和 engine，仅设置 storage；没有应用启动流程，见 [裸应用夹具](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_training_profiles.py#L33)。测试又只提供两个设置属性，见 [简化设置](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_invalidation.py#L439)。[lease 路径依赖](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin_leases.py#L16) 与 [缺配置即拒绝领取](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin_leases.py#L32) 需要 engine 上的配置绑定；生产应用入口在启动 worker 前执行 [initialize_settings](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/main.py#L59)，其绑定见 [engine 设置绑定](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin.py#L25)。

直接原因是运行夹具缺失，不足以证明正常启动的 worker 无法执行。但是 **provider 根本没有开始，撤销动作及迟到内容/错误的处理均未到达**，属于高关注验证缺口；任何绕开标准 lifespan 自行构建 worker 的入口也不能由本批记录获得保证。

R2/R3 共同的有限旁证：源码在报告回写、消息回写及失败重排前检查持久 job 仍为 running，分别见 [报告回写](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/analyst.py#L606)、[消息回写](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/analyst.py#L664)、[失败处理](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/analyst.py#L685)；同批 `test_memory_changes_preserve_inflight_session_but_revoke_chat_without_refunding_quota` 四个变体通过（[邻近撤销测试记录](raw/backend-tests.xml)）。这些不能替代上述 8 项更细的对象范围、任务删除与迟到结果测试。

### R4：4 项 attempts=1 断言仍把“领取”当成“实际 provider 调用”

B12–B15 在 claim/load 之间撤销 job；原始日志显示账本存在且为 failed，attempts=0。新实现只给 prepare 在领取时加次数；报告/消息在实际外呼前通过 `record_ai_attempt` 加次数，见 [领取语义](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin_scheduling.py#L258)、[实际调用计数](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin_scheduling.py#L284)、[report 先检查状态](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/analyst.py#L579)、[message 先检查状态](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/analyst.py#L616)。没有外呼时计 0 符合 [实际尝试契约](../../implementation/admin-contract.md)。

每日主动操作配额按保留的 job/payload 计数，独立于 attempts，见 [操作账本准入](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/analyst.py#L67)，因此 0 本身不代表退还配额或重置已发生调用。第 816 行之后的 payload、provider.calls、消息正文断言没有在这些失败用例中执行，不能补写为通过。已有实际尝试/恢复测试的通过记录在 [管理员调度与恢复结果](raw/backend-tests.xml)。

### R5：3 项 pose 产品流水线测试没有创建新要求的真实登记样本

B16–B18 的登记替身只返回 student/session ID，`_copy_gallery` 也被替换，不写 face/body 向量，见 [登记替身](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_pose.py#L271)。流水线现于 [登记后验证](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/research_engine/product_runner.py#L200) 调用 [持久图库验证](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/research_engine/src/identity/enrollment_validation.py#L30)，缺少有效样本即拒绝。旧 manifest 可以走 legacy 数量路径，但仍要求可用图库，见 [legacy 边界](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/research_engine/product_runner.py#L183) 与 [图库质量契约](../../implementation/task-sync-contract.md)。

直接失败不是标定精度门槛错误，也不是已有 pose 文件损坏；它发生在这些断言之前。**真实产品流水线的上下文传递、三种标定分支和输出拷贝/保留在这 3 项中均未验证**，不能用登记单元测试通过替代。不对真实 GPU/媒体处理作额外可用性判断。

### R6：1 项预置生成测试替换已不存在的模块级 GlmClient

B19 在 monkeypatch 第 149 行就失败，未进入 generate，见 [旧注入点](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_report_regressions.py#L149)。脚本现在创建应用、初始化配置并进入持久预置队列，见 [当前生成入口](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/scripts/generate_analyst_presets.py#L25)；已有结果复用逻辑在 [预置 worker](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/admin_presets.py#L49)。

这是测试注入边界过时，**完整 CLI 的旧预置原文保留、两种风格/语言及个人报告组合仍未由该测试验证**。同批 `test_preexisting_verified_preset_is_reused_without_provider_request` 通过（[其具体范围](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_admin_presets.py#L119)、[原始结果](raw/backend-tests.xml)），只提供单个已有变体不外呼、不覆盖的旁证，不能覆盖整个旧生成测试。

### R7：1 项迁移字典全等断言没有容纳 3 个新增列

B20 仅去掉旧预期的 analyst_locale 后比较整条 analysis 字典，见 [head 迁移后的断言](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_analyst_report_regressions.py#L239)。新迁移明确新增 enrollment_mode、expected_persons、sync_config_json，见 [加列迁移](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/migrations/versions/20260907_0013_task_sync.py#L11)。日志显示其余 19 个字段相同（[字典差异](raw/backend-tests.log)），没有显示旧字段丢失或被修改。后续 report 全等断言未执行；本项不能作为完整迁移/回滚或历史报告原文保留的通过证明。

### R8：1 项 readyz 测试仍要求现有数据库密码与环境初始化密码一致

B21 的差异是有意改变的账号权威来源：现有身份归数据库管理，bootstrap 不再比较或改写既有密码，见 [现有数据库分支](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/main.py#L23)、[现有账号契约](../../implementation/admin-contract.md)。新测试 `test_existing_database_does_not_promote_first_user_or_check_env_password` 在本批通过，见 [新预期](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_admin_auth.py#L83)、[结果](raw/backend-tests.xml)。

这不是日志已证明的认证绕过或擅自改密。不过 readyz=200 **不能证明环境中的密码能登录，也不证明现有数据库一定有可用管理员**；不能将该健康检查当作管理员可用性验收。

### R9：1 项注册响应精确相等断言未包含 role

B22 的四个原有字段相同，额外字段仅 `role: user`，见 [原始响应差异](raw/backend-tests.log)；字段属于当前 [UserPublic](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/models.py#L47) 契约。没有在此失败中看到管理员提权或身份归一化损坏。角色互斥与注册不能提权的测试另有本批通过记录（[管理员身份测试](raw/backend-tests.xml)），不改变本项失败状态。

### R10：3 项仍依赖旧 manifest/全局 sync 契约

- B23：预置 manifest 的原有六项相同，新增 lineup/4 注册信息；来自 [预置登记默认](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/presets.py#L19) 和 [manifest 扩展](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/presets.py#L145)，没有显示原摄像机或 group sync 路径被替换
- B24：只因失败检查集合不再含全局 sync_config 而失败，其他期望检查仍在；[任务独立同步](../../implementation/task-sync-contract.md) 明确新上传不复制全局同步；本批 `test_readiness_no_longer_depends_on_shared_upload_sync` 通过（[结果](raw/backend-tests.xml)）
- B25：测试已经执行确认并成功排队，却仍期待旧全局 offset 字典；[确认后旧断言](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/tests/test_tasks_api.py#L542)、[读取当前确认配置](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/api/routes/tasks.py#L381)、[写任务独立快照](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/services/storage.py#L318) 解释新结果。后续第 549 行仅允许旧 manifest key 集合的断言未执行，不能把整条提交用例记为通过

这些差异符合 [注册与提交契约](../../implementation/task-sync-contract.md)，不构成已证实的错机位、全局同步串用或排队失败。版本失效/快照行为有同批 task_sync 测试记录（[同步测试结果](raw/backend-tests.xml)），但不证明真实多机位视频已经正确对齐。

## 前端每项失败

| 编号 | 失败项 | 原始证据 | 归因与未完成部分 |
| --- | --- | --- | --- |
| F01 | desktop-chromium / api-center.spec.ts / API docs keep the public header contract and responsive navigation | [JSON](raw/frontend-e2e.json) · [log](raw/frontend-e2e.log) · [断言](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/tests/api-center.spec.ts#L27) | 旧契约：要求 analyses 文本为 0，实际为 1；后面的对比度、目录响应和 overflow 断言未执行 |
| F02 | mobile-chromium / 同名 API docs 测试 | [JSON](raw/frontend-e2e.json) · [log](raw/frontend-e2e.log) · [断言](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/tests/api-center.spec.ts#L27) | 同一旧断言；移动目录/菜单/overflow 的后续断言未执行 |
| F03 | desktop-chromium / public-foundation.spec.ts / logout can retry a network failure and clears access to protected pages | [JSON](raw/frontend-e2e.json) · [log](raw/frontend-e2e.log) · [断言](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/tests/public-foundation.spec.ts#L201) | 未验证：全局 alert 定位到退出失败提示和配额失败提示两个节点；后续重试、清 cookie 后权限、焦点及刷新检查均未执行 |
| F04 | mobile-chromium / 同名 logout 测试 | [JSON](raw/frontend-e2e.json) · [log](raw/frontend-e2e.log) · [断言](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/tests/public-foundation.spec.ts#L201) | 同一夹具/定位阻断，不能据此判定移动退出失效，也不能声称重试成功 |
| F05 | Vitest / ApiCenter.test.tsx / API center publishes an accurate public task API guide in the dedicated shell | [JSON testResults / assertionResults](raw/frontend-unit.json) · [断言](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/src/ApiCenter.test.tsx#L61) | 旧契约：禁止 analyses 文本，发现单次上传端点；后续导航内容排除断言未执行 |

F01/F02/F05 的新增端点文档是明确需求，不是意外泄露内部接口：[单次上传说明](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/src/pages/ApiDocsPage.tsx#L218) 对应现有 [真实上传路由](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/app/api/routes/analyses.py#L86) 和 [单次上传契约](../../implementation/task-sync-contract.md)。这 3 项不能证明文档全部准确，但观察到的差异有直接契约依据。

F03/F04 的夹具对未覆盖 API 一律返回 404（[默认 mock](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/tests/public-foundation.spec.ts#L10)），没有提供当前配额读取所需响应。当前组件读取 usage 与 limits，失败时展示独立 alert，见 [当前配额请求与错误状态](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/src/pages/ApiDocsPage.tsx#L117)；退出失败也有自己的 alert，见 [退出错误提示](https://github.com/Siyuan-Xue/dashanbing-backend/blob/eff724d27266112bac12594ed367fed0d221c4f2/frontend/src/components/PublicHeader.tsx#L109)。原始日志明确显示两个提示，故直接失败是严格定位歧义，不能把配额提示归因于真实服务端故障；同样不能在没有执行第 202–217 行的情况下声称重试与权限清除已通过。

## 可引用的旁证和仍需保留的边界

指定 XML 中 `tests.test_admin*` 共 75 项、0 失败；指定 unit JSON 中 AdminControls 3、AdminRouting 6、AdminOverviewPage 3、AdminPage 6 项全部记录通过，合计 18。这是本次集中产物中的事实，不能覆盖上述失效竞争、完整 CLI、流水线产物或前端失败尾部的未验证范围。

本报告不提出改断言后复测、不进行优化验收循环，也不把“根因是旧契约/夹具”当作产品验收通过。重点风险排序为：**8 项撤销后写回/隔离/账本场景未验证 → 3 项流水线产物及 1 项生成 CLI 未验证 → 前端退出重试尾部未验证**。其余契约差异保留为原始失败，是否接受这些验证缺口由最终验收记录决定。
