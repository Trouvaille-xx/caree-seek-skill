# 浏览器能力契约（browser contract）

CareeSeek 不直接驱动浏览器。**浏览器操作由宿主 agent 用它的浏览器 MCP/工具完成**；脚本只处理数据。
本文件定义统一的 9 个语义操作、探测顺序与各工具适配要点。

## 1. 统一操作

| 操作 | 参数 | 期望返回 | 用途 |
|---|---|---|---|
| `navigate` | url | ok, final_url, title | 打开首页/搜索页/详情页 |
| `read_text` | — | 页面纯文本 | 登录墙/验证码/列表存在性判断 |
| `read_dom` | selector? | 匹配元素文本列表 | execute_js 不可用时的降级抽取 |
| `click` | selector 或 ref | ok | 关闭弹窗、翻页、切换城市 |
| `type` | selector, text | ok | 搜索框输入 |
| `screenshot` | — | 图片 | 人工升级、排查、验证码暂停 |
| `scroll` | direction, amount | ok | 触发懒加载 |
| `execute_js` | script | 脚本返回值 | **首选抽取方式**（见 extract-*.js） |
| `profile_reuse` | — | 语义：登录态可跨页面/会话保持 | 判断是否需要每次登录 |

`profile_reuse` 不是具体工具名，而是一个判断：同一浏览器会话里登录态是否稳定复用。
若工具每次都是全新无痕环境，则视为不支持。

## 2. 探测顺序

按以下优先级实测，第一个通过者写入 `state.json` 的 `active_adapter`：

1. **ego-browser** — 使用用户本人的 Chromium profile，通常自带登录态。首选。
2. **Claude-in-Chrome** — 控制用户真实 Chrome，天然复用登录态；有 tab/ref 概念与 `javascript_tool`。
3. **Playwright MCP** — 独立浏览器；除非配置了持久化 profile，否则登录态弱。`browser_evaluate` 可执行 JS。
4. **tabbit** — CLI 驱动，按具体实现映射；同样优先确认登录态。

探测步骤（每个候选都做一次，约 10 秒）：
1. `navigate` 到 `https://www.zhipin.com`
2. `read_text`，确认页面包含「Boss直聘 / 直聘 / 职位」等特征，且没有测试环境错误
3. 记录是否命中 `login_wall_patterns`（未登录也可，后续登录）
4. 通过 → 写状态：

```bash
python scripts/ingest.py --run <run> --state-set active_adapter="ego-browser"
```

全部失败 → 停止，向用户输出安装提示（不要尝试无浏览器方案）。

## 3. 各工具适配要点

### ego-browser（推荐）
- 使用用户已登录的真实浏览器 profile；先调用其 skill/CLI 打开或接管浏览器。
- 抽取优先用其页面执行能力跑 `references/extract-list.js` / `extract-detail.js`。
- 优点：真实指纹、真实登录态、可被用户实时看到；对风控最友好。

### Claude-in-Chrome
- 先 `tabs_context_mcp` 取得 tab，再 `tabs_create_mcp` 新建标签页。
- 抽取用 `javascript_tool`（页面上下文执行）跑 extract 脚本。
- 点击可用 ref（`read_page` / `find` 获得）或坐标；坐标点击前先截图确认。
- 注意：不要复用无关会话的 tab。

### Playwright MCP
- 用 `browser_navigate` / `browser_snapshot` / `browser_click` / `browser_type` / `browser_evaluate`。
- `browser_evaluate` 里可直接传入 extract 脚本的函数体。
- 若无持久化 profile：明确告知用户「每次可能需要重新登录」。
- 无头模式更容易触发风控，优先有头模式。

### tabbit
- 按其 CLI 的导航 / 执行 / 截图能力映射上述 9 个操作。
- 同样优先验证登录态复用。

## 4. 抽取策略优先级

1. `execute_js` 运行 `extract-list-api.js`（设置 `window.__CAREE_PARAMS__`）：同源接口返回明文薪资与公司元数据，最稳。
2. 接口失败：`execute_js` 运行 `extract-list.js` / `extract-detail.js`（DOM 抽取）。
3. 不支持 JS 时：`read_dom` + `selectors.json` 的字段提示 → 由 agent 自行映射。
4. 最后手段：`screenshot` + 视觉读取（慢、易错，仅兜底）。

> 注意：Boss 列表页的薪资数字由自定义字体渲染，DOM 文本不可读；因此接口优先，DOM 兜底时接受薪资缺失。

## 5. 状态回写

agent 每完成一个阶段，用 `ingest.py --state-set` 回写，避免丢进度：

```bash
python scripts/ingest.py --run <run> --state-set active_adapter="ego-browser"
python scripts/ingest.py --run <run> --state-set logged_in=true
python scripts/ingest.py --run <run> --pages-done 3
```

## 6. 失败处理

- 页面打不开 / 反复报错 → 换下一个候选工具。
- 命中登录墙 → 进入登录流程（playbook §2）。
- 命中验证码 → 立即暂停并请用户手动处理（playbook §6），**不得尝试自动绕过**。
- 所有候选都不可用 → 终止自动采集，并给用户两个可执行选项：
  1. **安装/启用任一浏览器工具**：ego-browser / ego lite、Claude-in-Chrome、Playwright MCP（如 `npx @playwright/mcp@latest`，优先有头模式）、tabbit。装好后重跑探测。
  2. **改用已有数据**：如果用户手上有调研工作簿，运行
     ```bash
     python scripts/import_xlsx.py --run <run> --xlsx "<path>"
     ```
     跳过浏览器采集，直接做归一化、分析、报告与简历匹配。
- **不要**用 `requests` / `curl` 直接抓 Boss 直聘：没有登录态、容易触发风控，也违反平台条款。没有浏览器就是没有自动采集能力，要如实告诉用户。
