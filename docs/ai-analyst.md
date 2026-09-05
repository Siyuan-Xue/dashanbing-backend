# AI 分析师

结果页按照视频、AI 分析师、原始概览/时间线/JSON 排布，AI 作业独立于 GPU 视频分析队列

## 配置与运行

按 `.env.example` 配置服务端 `GLM_API_KEY`，不在前端配置 Key
按 [GLM-5.3 官方文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3) 使用模型 API 的 Chat Completion 端点，保持思考开启，默认 max、temperature 1、最大输出 65536 tokens
`BASKETBALL_GLM_TEMPERATURE` 可设置为 0–1，最多两位小数
通过 `BASKETBALL_GLM_REASONING_EFFORT`、`BASKETBALL_GLM_MAX_TOKENS`、`BASKETBALL_GLM_TIMEOUT_SECONDS` 调整调用，默认超时 600 秒
`BASKETBALL_ANALYST_CONCURRENCY` 默认 2，`BASKETBALL_ANALYST_DAILY_LIMIT` 默认每人每日 100 次主动追问和生成
未设置 Key 时显示尚未启用，视频任务和原始结果继续正常工作
升级时先运行 `alembic upgrade head`，再启动单个应用进程，持久队列在重启后恢复
Compose 保留本机 8000 端口绑定，应用网络允许向智谱发送 HTTPS 请求，旧的 internal 网络会阻止该请求

## 数据边界

事实来自当前任务最终输出，事件通过片段和球员双重关联投篮结果，所有统计由后端计算
不向 GLM 上传视频、图片、人脸特征、内部身份编号或服务器路径
只有验证过来源、身份和标定的姿态数据可提供肘膝角度，缺失条件时保留基础复盘
用户手动把本场球员关联至长期球员档案，追踪编号不会自动成为跨任务身份
同一组四路视频的重复运行按输入内容去重，个人目标和备注由用户确认，模型不会自动修改记忆
首次关联档案后默认选择同档案、同模式、共同动作的最近有效训练，之后显式选择不对比会持续保留
混合动作只部分相同时标记汇总投篮指标不可直接比较，个人比较使用个人统计
视频自然到期时保留已确认训练摘要，主动删除任务则移除其派生记录，报告及聊天按账户隔离
修改档案或训练关联时只清理依赖被修改内容的 AI 快照，保留无关报告、合法比较选择和已使用的配额

## 真实首页素材

先完成前端，再为现有样例生成真实 GLM 报告：

```
python scripts/generate_analyst_presets.py --presets quick-demo --locales zh en --styles coach
```

生成脚本没有 Key 时直接退出，不生成模拟报告
报告保存在 runtime/analyst-presets，带有当前样例事实摘要的校验值
示例接口仅接受校验匹配、模型为 glm-5.3 的已验证报告，首页使用截图静态资产，不触发模型调用
前端截图脚本从该接口确认真实报告后，采集桌面和移动页面及分析师局部，随后生成首页素材清单
生成后的截图不应含用户邮箱、真实姓名或内部路径
完整操作见 [截图脚本说明](../frontend/scripts/README-analyst.md)，主图与局部图共 16 份静态 WebP，按语言、主题和设备选择

## 接口

- GET/POST `/api/v1/tasks/{id}/analyst/report`，读取/请求生成报告
- GET/PUT `/api/v1/tasks/{id}/analyst/context`，选择球员档案、训练组和历史比较
- `/api/v1/training-profiles`，档案创建、编辑、删除及历史查询
- POST `/api/v1/analyst/conversations`，创建当前用户的任务/示例追问会话
- GET `/api/v1/analyst/conversations/{id}`，恢复已保存的问答
- POST `/api/v1/analyst/conversations/{id}/messages`，使用 request_id 幂等提交问题
- GET `/api/v1/analyst/conversations/{id}/events`，SSE 发送 message 快照和 done 事件
- GET `/api/v1/presets/{id}/analyst/report`，只读示例报告

所有工作台接口保留现有登录或 API Key 鉴权

## 当前验收范围

代码、迁移、模拟 GLM 回归、浏览器交互和构建已验证，配置方式只涉及服务端
GLM Key 尚未提供，真实调用、最终报告质量验收及首页正式截图待 Key 接入后完成
科研几何与当前任务输入链路已有回归测试，本地未执行真实 GPU 推理
现有样例标定未通过分析师质量门槛时，不提供三维姿态指标，保留动作、投篮及视频证据复盘
