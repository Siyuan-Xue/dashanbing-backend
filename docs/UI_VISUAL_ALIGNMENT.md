# MinerU visual alignment

The approved redesign preserves all basketball functionality, routes, authentication,
API contracts and data. Reference surfaces: https://mineru.net/,
https://mineru.net/apiManage/docs, https://mineru.net/apiManage/token and
https://mineru.net/OpenSourceTools/Extractor (including task management, demo results
and settings). Reference inspected on 2026-09-05.

## Implementation areas

1. Shared styles, supplied transparent logo, public header, centered home and auth.
2. API shell, hierarchical anchored docs and full-width API management.
3. Workspace shell, single-row sidebar footer, tasks/results/settings.
4. Responsive screenshot matrix, behavioral regression and final review.

## Design contract

- Public/API: system font, white canvas, #121316 text, #F4F5F9 surfaces,
  subtle 1px borders, black primary actions. Dark theme reverses contrast.
- Home: centered 48px/600 desktop title, 32px mobile title; badge, description,
  paired actions, full-width basketball preview, three capability accordion items,
  two broad example sections, centered CTA and restrained footer.
- Logo: preserve supplied orange basketball and faceted blue iceberg; remove only
  exterior white background and margins, preserve white snow and highlights.
- API: 210px sidebar; docs plus 196px TOC capped at 1200px; body 16px, table 14px,
  chapter 26px, subheading 21px. Eight original anchors survive. Children cover
  create/upload/submit, polling/result/media, Curl/Python. Heading metadata also
  drives nested TOC; current heading, deep links and history must work.
- Keys page fills space beside sidebar, with all four actual quotas, compact token
  panel and existing create/revoke/one-time-secret behavior.
- Workspace: 260px desktop sidebar, compact rows and a SINGLE ROW footer with
  circular account control on the left and GitHub/API/settings on the right.
  Footer must not remain a two-row username card. Keep accessible account name.
- >=1280px full desktop; 768-1279px inline expandable TOC and collapsible workspace
  sidebar; <768px public menu, inline collapsible API nav, workspace drawer.
  Result panes stack when necessary. Tables/code scroll locally, never clip the page.
- Preserve both languages and themes, focus handling, Escape and reduced motion.
- Do not add client/ecosystem/news, document parsing features or change backend.

## Validation

Run unit tests, typecheck, build and existing E2E. Extend screenshot coverage to all
ten routes, modal and empty states; light/dark and zh/en at 390/768/1024/1440/1920.
Also exercise 320px, breakpoint boundaries and short windows. Capture reference
and product at equal viewport sizes, visually inspect and establish regression
baselines only after review. No production deployment is included.

## 交付与逐页检查

实现分支：`codex/mineru-visual-polish`。最初交付不包含部署；用户随后授权生产发布。最新跟进见文末。

[截图查看器](visual-review.html) 提供 10 个页面的宽度、语言、主题切换，以及弹窗、空状态、下方内容和断点截图。截图对应入口和改造说明在每张图上方。参考站通过 Browser 检查；首页保留用户提供的原始对照图，其余参考页面保留入口链接，未将参考站账户数据保存到仓库。

| 页面 | 最终检查内容 |
| --- | --- |
| 首页 | 居中首屏、48/32px 渐变标题、黑色主按钮、宽幅篮球预览；三项能力手风琴、两个示例及页脚 |
| 登录 / 注册 | 480px 居中卡片、统一 Logo 和表单；登录后的目标页恢复及注册校验 |
| 创建任务 | 260px 侧栏、单行底部工具、五路视频槽位、示例入口和提交状态 |
| 任务列表 | 紧凑标题、筛选、表头行高、状态、分页与删除确认 |
| 任务 / 示例详情 | 顶部工具栏、等宽双栏、窄屏纵向排列；媒体和结果标签及局部滚动 |
| 设置 | 页内导航、四项用量配额、保留规则、持久化语言和主题设置 |
| API 文档 | 210px 产品导航、宽正文、196px 分级目录；8 个原有章节及子级锚点 |
| API 管理 | 全宽配额与密钥面板；创建、撤销、有效期、一次性密钥展示 |

工作台底栏展开时为 **48px 高的单行**：左侧圆形账户入口，右侧 GitHub、API、设置。收起后隐藏整个固定侧栏，顶部显示菜单和 Logo；鼠标悬停浮出边栏，点击固定展开。手机使用可关闭抽屉。矮窗口可滚动访问底部工具。

## Logo 资产

统一资产：[`dashanbing-mark.svg`](../frontend/public/assets/brand/dashanbing-mark.svg)。SVG 内嵌用户原始 PNG，通过外轮廓裁切和紧边 viewBox 去除外围白底；原图像素逐字节保留，篮球纹理、冰山白色雪面和高光不变。页眉、工作台、登录注册、首页预览、页脚和 favicon 使用同一资产。未采用重新生成的近似 Logo。

## 自动验证记录（2026-09-05）

最终源代码已通过：

- Vitest：**79 passed**，4 个测试文件。
- TypeScript：`pnpm typecheck`，无错误。
- Production build：`pnpm build`，成功，82 个模块；构建产物位于既有 `app/frontend` 输出目录。
- 功能 E2E：**56 passed、26 skipped**。跳过项为已有的桌面专用场景或避免手机项目重复显式视口检查。
- 全部 E2E 与视觉矩阵联合运行：**346 passed、26 skipped**，无失败。
- 语言切换定位场景在桌面与手机重复运行：**20/20 passed**。
- `git diff --check` 通过；后端、OpenAPI、生成的 API 类型和依赖锁文件无变更。

功能用例包括登录跳转、五槽位上传和失败重试、提交门槛、任务操作、媒体切换与加载/失败/重试、摘要/时间线/JSON 切换、目录深链和浏览器历史、密钥创建/撤销/一次性显示、弹窗焦点和背景滚动、抽屉 Escape/焦点恢复、菜单随路由关闭。

截图矩阵：

- 10 页面 × 5 宽度（390、768、1024、1440、1920）× 2 语言 × 2 主题，**200 张首屏基线**。
- 首页下方、API 上传章节、密钥/任务弹窗、空状态、移动导航，**72 张状态基线**。
- 320×700、767×800、769×800、1279×800、1281×800、1440×480、1024×320，**70 张边界截图**。
- 合计 **272 张回归基线 + 70 张边界截图**。基线保存在 [`visual-matrix.spec.ts-snapshots`](../frontend/tests/visual-matrix.spec.ts-snapshots/)，边界截图在 [`visual-boundaries`](visual-boundaries/)。

首屏截图比对允许最多 0.1% 像素差异；普通正文横向溢出另以实际文档宽度断言检查。代码、表格和 JSON 使用区域内滚动。全部最终截图重新生成后，单独执行不更新基线的视觉回归：**290 passed（50.8 秒）**。查看器脚本语法和全部 342 张产品图片路径均已检查。

## 复现

在 `frontend` 中运行（需要 Node、pnpm 与 Playwright Chromium）：

```sh
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test
pnpm typecheck
pnpm build
pnpm exec playwright test --workers=6
```

单独视觉回归：`pnpm test:e2e:visual`。只有在人工确认视觉变更后，才使用 `--update-snapshots` 更新基线。

本地开发与构建显式使用 `vite.config.ts`，避免旧的生成版 JS 配置将 `/api/docs` 错误代理到后端。开发预览为 `http://127.0.0.1:5173`。

## 验证范围

测试使用确定的模拟账户、任务、配额及 API 响应，不向生产账户提交任务或创建密钥。结果页截图采用媒体空状态；功能用例覆盖媒体选择、加载、错误和重试，未验证真实 GPU 分析任务或完整视频解码。测试浏览器为本机 Chromium，截图基线带 `darwin` 后缀；其他操作系统或浏览器应在对应环境另建字体渲染基线。

参考站与大山冰内容不同，未进行跨产品逐像素差异评分。对齐的是布局、字体层级、颜色、控件、目录及响应式行为；保留篮球业务内容，并按计划修正参考站在窄屏上的拥挤。静态 HTML 查看器受当前 Browser 的 `file://` 策略限制未直接打开，已校验所有图片路径；页面本身通过 Playwright 截图和回归验证。


## 本轮跟进：蓝 / 棕红品牌与工作台（2026-09-05）

以用户最新截图和反馈覆盖最初方案中的紫色、60px 图标栏及左右结果布局：

- 冰山蓝主色 `#1678A6`，棕红强调色 `#9B4436`；深色对应 `#73C9ED`、`#E6A598`。同步 CSS 与主题初始化脚本，移除紫色渐变标题与紫色光晕。主色按钮浅色白字对比度约 4.92:1。
- GitHub 图标按用户最终要求恢复第一次放大之前的原始形状与样式，页眉 20px、工作台底栏 18px、首页预览 16px。
- Logo 生产故障来自 `/brand/...svg` 被 SPA 回退路由作为 HTML 返回；统一改到已挂载的 `/assets/brand/...svg`，favicon 同步。
- 右侧为无外层圆角、无外边框的连续内容区域。任务列表使用白底轻分隔线、顶部搜索/筛选弹层、图标操作、底部分页及每页条数。
- 侧栏固定展开宽 260px；收起后内容使用全宽，顶部保留菜单与品牌。鼠标悬停菜单浮出 260px 侧栏，不推动正文；点击固定展开。支持移出关闭、Escape、ArrowDown 进入导航、路由切换关闭及焦点恢复。手机仍采用独立抽屉。
- 结果页统一上方全宽 16:9 视频、下方解析结果。概览保留在布局流中，时间线/JSON 绝对定位并内部滚动，切换时保持概览高度；以 100 个事件及多条警告检查长内容。
- 删除上传槽位重复的“必需视频”、列表/设置等显然易懂的说明。删除、重试、上传、复制、下载、筛选及分页使用图标，保留悬停提示、无障碍名称及必要的确认文字。
- 首页预览按网页工作台重建，移除 macOS 三色窗口按钮与抽象篮球场示意。四个机位、人物骨架、球/篮筐检测及动作阶段均来自实际示例视频；显示真实快速示例的 4 次出手、2 次命中、4 名注册参与者、4 次动作。

截图素材可通过 `.venv/bin/python scripts/export_frontend_previews.py` 重建。脚本直接解码现有视频帧，保留完整画面与模型原始标注，未生成虚构球员或检测结果。9 张 WebP 的来源、时间点和 SHA-256 记录在 `frontend/public/assets/previews/sources.json`。原始机位按 `group_04.json` 的时间偏移取帧，快速示例为约 6.15 秒。

最终截图矩阵扩展为 **308 张基线 + 70 张边界截图**，新增收起/悬停/固定展开、筛选弹层、三个结果标签和首页真实视频预览。原视觉基线已完整重建；生成阶段 **298 passed**。交互测试使用模拟 API，GPU 分析流程未重新运行。


### 前次生产发布记录（24px 图标版本）

- Vitest：79 passed；TypeScript 与生产构建通过，83 个模块。
- 最终功能与视觉联合回归：355 passed、27 skipped，无失败。截图基线重建后以不更新基线方式验证。
- 2026-09-05 已发布到用户提供的生产服务器，仅更新静态前端，无服务重启、数据库修改或分析任务操作。
- 更新前完整备份：`/root/autodl-tmp/dashanbing-backend/app/frontend-before-refinement-20260905`。资源先复制，最后原子替换 HTML；保留旧哈希资源供已打开的页面使用。
- 当前构建：`assets/index-BdpKShKR.js`、`assets/index-ByynxQfa.css`。生产端及 HTTP 下载的 15 个文件均与本地 SHA-256 一致。
- 真实生产浏览器验证覆盖 1440/390px × 浅/深主题：Logo SVG 正确解码；9 张预览均解码为 1920×1080；GitHub 为 24×24px、实心填充；品牌色正确、无文档横向溢出、无页面脚本异常。
- Logo MIME 为 `image/svg+xml`。服务器现有 MIME 数据库对 WebP 返回 `application/octet-stream`，已逐张验证真实 Chromium 解码成功；未为此更改后端或重启服务。
- 生产健康检查：`status=ok`、`ready=true`、GPU 模式，15 项就绪检查。未提交新的生产 GPU 任务。

生产验证记录：[verification.json](production-verification/verification.json)。生产截图保存在 [production-verification](production-verification/)，交互查看器为 [visual-review.html](visual-review.html)。


### 合并 main 前的最后调整

GitHub 图标按用户最终要求完整恢复到第一次放大之前的原始形状、尺寸与样式。首页仅将中文主标题改为用户指定的“让我看看你打球什么b样”，其余首页文案、按钮及英文文本恢复修改前版本；首页句号移除或换为逗号。

前次生产截图保留于上节，最新页面以 308 张回归基线与 70 张边界截图为准。最终变更包含此前已部署但尚未提交的整套前端改造，统一通过功能分支 PR 合并 main。

本次最终验证：79 项单元测试通过，类型检查及构建通过，完整功能与视觉回归 355 passed、27 skipped，独立代码审查无重大问题
