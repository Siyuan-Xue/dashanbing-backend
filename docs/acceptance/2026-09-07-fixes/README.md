# 验收后修复记录

本轮从 `bf0ff0ee3bd96abb7e5bf51a31dacf1a0c7edde3` 开始，按后续指示修复实际缺陷，将性能要求改为[测量与观察规则](performance-policy.md)。原 [2026-09-07 验收证据](../2026-09-07/README.md) 完整保留，以下是独立的修复后结果

最终产品代码基线：`a95121d93128077f3a6b5a2ca3c64808687f72be`，与两份发布文档一致

## 已定位的问题

| 问题 | 根因与修复 |
| --- | --- |
| GPU 启动时 OSNet 无法加载 | 科研入口过早导入身份模块，间接缓存默认模型和任务目录；改为配置任务路径后再导入，补充独立进程回归 |
| 预置 AI 报告全部返回上游错误 | `preset-` 前缀加 64 位作业摘要生成了 71 位请求标识；改用原有 64 位摘要，保留作业 ID、去重和调用账本 |
| 管理员搜索框图标与输入框错行 | `.task-filters label` 覆盖了搜索框 Flex 布局；修正样式优先级，同时给账户信息列保留宽度，表格使用局部滚动 |
| 768px 角色检查误报 | 脚本等待处于抽屉中的导航可见；改为等待实际管理页标题，保留路由、禁止数据请求和服务端 403 检查 |
| API 文档、退出登录及后端测试失败 | 测试仍沿用旧契约或缺少真实服务需要的夹具；同步一次上传、持久化配额、角色及注册/同步字段，补齐撤销竞态和有效图库样本，不降低权限或数据要求 |
| Mac Safari 同步按钮无法点击 | WebDriver 返回 `element not interactable`，按钮位于视口外；明确桌面视口，使用浏览器滚动后再执行真实点击，保存安全错误码 |
| AI 领取使请求无法及时回滚 | 同步 SQLite 写锁等待发生在事件循环中，请求释放事务又需要事件循环；将领取移至线程，保持事务校验与原并发上限 |
| 停止时领取异常或重复取消 | 独立审查发现异常可能覆盖取消信号、第二次取消可能遗留 lease；等待被保护的领取与清理任务结束后继续抛出取消，保留红测与复核记录 |
| 视频领取因忙锁退出 | 领取异常发生在原循环的异常处理之外；修复范围限于领取、停止和异常恢复，不调整生产忙锁超时或视频执行并发 |

GLM 请求标识长度限制依据[智谱官方对话补全文档](https://docs.bigmodel.cn/api-reference/模型-api/对话补全)。在同一服务器、同一模型与 Key 下，71 位标识返回 HTTP 400，39 位对照标识调用成功。修复没有更换 Key、模型或生成参数

## 已完成的验证

- 后端测试：865 项通过，0 失败/错误/跳过，79.39 秒，24 条既有 Alembic 警告
- 前端单元测试：264 项通过
- 与原验收相同范围的 Chromium 功能 E2E：181 项通过、61 项跳过，无失败，重试为 0
- TypeScript 与生产构建通过，既有主包大于 500 kB 的提示保留
- 管理员页面真实 Chrome：16 个页面组合和 32 组角色边界检查，没有检测到失败或全页横向溢出；人工复核了窄屏搜索、账户列及用量列
- 真实 Mac Safari：19 个步骤完成，覆盖五槽位草稿恢复、逐帧、四路选帧、取消不保存、确认精确时间及返回后恢复；视频为隔离的合成 CFR 测试素材，不代表篮球识别准确性
- 真实 GPU 严格启动探针通过，实际加载现有模型并执行空帧推理；端到端视频任务结果另行记录，不能用探针代替
- 使用四组已有真实篮球结果生成中文全场与球员、两种语气共 40 个预置版本：39 个发布成功、1 个最终失败，共耗时约 591 秒

AI 共记录 62 次实际调用，峰值并发 8，41 次供应商成功响应、21 次限流错误；供应商成功响应不等于报告通过校验并发布。唯一最终失败的版本先收到成功响应但未发布，随后两次调用被限流；未保存首份未发布响应，无法追溯其具体校验或写入错误。没有修改有限重试次数，也不把最终失败改写为成功

成功供应商响应的等待时间中位数约 45.81 秒、P95 约 100.90 秒，累计报告用量为 203,741 token。上述用量和等待仅属于这批预置生成，不包含最小诊断调用，不代表其他负载或供应商额度保证

## 输入与真机限制

逐帧读取 16 路原素材时间戳，12 路存在 33–67ms 的异常间隔，均标称 60fps。每组至少一路不符合当前恒定帧率校验，原文件未转换或截断，规则也没有为样例单独放宽

| 样例 | 检测到异常间隔的机位 | 异常间隔数 |
| --- | --- | ---: |
| quick-demo | 1、2、3、4 | 4 |
| mixed-actions | 1、2、4 | 5 |
| verified-outcome | 1、2、3 | 4 |
| layup-demo | 1、3 | 2 |

最终 v3 使用修复后的两类领取器和 180 秒 HTTP 观察窗口，四组样例的快速/完整共 8 次提交均返回 422 `unsupported_timeline`，耗时范围 19.63–70.02 秒，总计约 333.54 秒；这是输入检查耗时，不是 GPU 执行耗时。没有提交成功或可用任务运行时长、吞吐、峰值显存。同期独立账户限额读取返回 200，约 42ms，仅作为读请求可完成的旁证，不构成延迟保证。最终隔离服务收到 SIGINT 后正常关闭

中间 v2 测量的临时包装器错误地对 `http_request` 在非成功状态下返回的 `None` 读取错误字段，导致部分 HTTP 拒绝被归为 transport_error；另有真实观察超时。该记录按工具缺陷原样保留，不能用其八个 error 推导八次相同业务失败，最终验证另列

iPhone Safari 真机认证成功、目标可见且命中，但驱动原生输入未形成完整可信 click，最终停在 `open_draft`。无业务处理器的最小按钮同样复现；键盘可以导航仅是对照，不算触摸验收。后续视频同步步骤保持未执行，具体外部驱动原因未确定，没有据此修改产品点击逻辑或要求用户反复改设置

## 额外视觉回归与范围

额外运行了历史截图项目，162 项匹配、148 项出现差异。该基线来自 `0656887`，早于当前界面；抽查可见 GitHub 标识、Lucide 图标和首页预览控件变化。未逐一审核这 148 项，全部保留为未完成的视觉基线核对，不按“历史截图”自动判为通过，也未重写快照或调大像素容差

这项额外截图项目与上面的 181 项功能 E2E 分开统计。原图、差异图和日志保存在本地忽略目录 `runtime/closeout-fixes/frontend/full-artifacts` 与 `runtime/closeout-fixes/frontend/e2e-full.log`

原始修复日志位于 `runtime/closeout-fixes`，不包含生产变更。本轮不执行生产部署、账户迁移、生产备份或定时任务，凭据、数据库与私有视频不进入 Git

## 证据入口

| 材料 | 位置 |
| --- | --- |
| 后端最终与缺陷红绿记录 | [后端结果](raw/backend-tests.log)、[JUnit](raw/backend-tests.xml)、[修复说明](backend-fixes.md) |
| 前端单测、功能 E2E 与构建 | [单测](raw/frontend-unit.log)、[E2E](raw/frontend-e2e.log)、[构建](raw/frontend-build.log) |
| 历史视觉差异 | [包含全部失败的日志](raw/frontend-extra-visual.log) |
| Chrome 与 Safari | [16 页面及 32 组边界](raw/chrome-admin.json)、[Mac 19 步](raw/safari-mac.json)、[Mac 断点](raw/safari-mac-breakpoints.json)、[iPhone 失败](raw/safari-iphone.json) |
| 模型与输入 | [严格探针](raw/gpu-readiness.json)、[逐帧时序统计](raw/source-timeline.json)、[最终八组提交](raw/gpu-final.json) |
| GLM | [39/40 结果与用量](raw/glm-summary.json)、[全部调用](raw/glm-calls.jsonl) |
| 代码审查 | [发现及修复复核](code-review.md) |
| 文件校验与脱敏 | [原文件和发布副本哈希](evidence-manifest.json)、[交付校验](checksums.json) |

代表截图：[管理员窄屏深色](screenshots/admin-390-en-dark.png)、[管理员窄屏浅色](screenshots/admin-390-zh-light.png)、[Safari 四机位](screenshots/safari-mac-four-cameras.png)、[Safari 已确认同步](screenshots/safari-mac-confirmed.png)。管理员亮色遮挡块为测试账号采集遮罩，Safari 视频使用合成素材

复用原测量和截图脚本；后端修复回归在 `tests/test_analyst_claim_liveness.py`、`tests/test_video_claim_liveness.py`、`tests/test_product_runtime_bootstrap.py`，浏览器工具回归在 `tests/test_safari_product_flow.py` 和 `tests/test_browser_closeout.py`。完整原始数据留在忽略的 runtime 目录，发布 JSON 脱敏设备标识及工作树路径，日志副本去除行末空白，原文件哈希保留，未删除失败或修改数字
