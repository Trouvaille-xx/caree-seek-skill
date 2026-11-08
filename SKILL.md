---
name: caree-seek
description: 求职市场情报检索与分析。到 Boss直聘按用户的求职意向（城市、经验年限、目标岗位、行业、期望薪资）检索岗位，产出三件套：多 sheet 汇总 Excel、ECharts 交互式岗位 seek 报告、简历 × 岗位匹配 HTML 报告。分析涵盖月薪分布、城市×公司梯队、岗位阶梯（同司职级 / 跨司对标 / 能力地图 / 薪资曲线）、创始人·管理层公开信息背调；有简历时做匹配排序、差距分析、简历优化与冲/稳/保投递建议。当用户提到「求职市场调研」「岗位分析」「薪资报告」「Boss直聘 拉岗位」「公司背调」「简历匹配」「offer 对比」时使用。
version: 0.1.0
---

# CareeSeek — 求职市场情报 skill

帮助求职者从一个求职意向出发，完成：**意向访谈 → 浏览器检索招聘平台 → 数据结构化 → 阶梯/薪资/背调分析 → HTML 报告与导出**。

核心分工：**浏览器操作由宿主 agent 通过其浏览器工具完成；Python 脚本只处理数据、分析与报告**。因此本包可以装进不同 agent harness（Claude Code、Codex、DeepSeek 等）。

## 何时使用

- 用户想了解某个城市 / 岗位 / 行业的真实薪资与机会分布；
- 用户想比较不同公司的同职级岗位、或看同一公司的职级阶梯；
- 用户想在做 offer 决策前做公司与创始人/管理层的公开信息背调；
- 用户明确提到 Boss直聘 或国内招聘平台。

## 硬规则（不可越过的红线）

1. **不做自动投递、自动打招呼、自动私信。** 只检索与分析。
2. **不绕过验证码、登录墙、访问控制。** 遇到风控信号立即暂停，交给用户手动处理。
3. **不采集个人隐私**（HR 姓名、联系方式等）。
4. 单次抓取 ≤100 条，低频、单标签、串行；首次建议保守节奏。
5. 报告与数据必须附带 `references/compliance.md` 的合规声明。
6. 公司风险只能是「待核实线索」，必须带来源与日期，不能做事实认定。

## 前置条件

- Python 3.9+（`python --version` 自检；未安装时提示 `winget install Python.Python.3.12`）。
- 至少一个浏览器工具：priority 为 **ego-browser → Claude-in-Chrome → Playwright MCP → tabbit**。
- 背调阶段需要宿主具备 Web 搜索能力（任意 harness 的搜索工具均可）。

## 工作流

### 阶段 0：意向访谈

按 `references/intake-questionnaire.md` 与最终用户确认 10 个问题（全部可跳过），写入 `answers.json`，然后：

```bash
python scripts/intake.py --run runs/<run_id> --answers answers.json
```

### 阶段 1：环境自检 + 浏览器探测

```bash
python scripts/preflight.py
```

按 `references/browser-contract.md` 实测浏览器工具并回写：

```bash
python scripts/ingest.py --run <run> --state-set active_adapter="ego-browser"
```

无可用浏览器 → 停止并给安装提示。

### 阶段 2：登录（一次）

按 `references/playbook-boss.md` §2 检测登录墙；需要时请用户在浏览器内手动登录，成功后：

```bash
python scripts/ingest.py --run <run> --state-set logged_in=true
```

### 阶段 3：搜索 + 列表采集

严格按 `references/playbook-boss.md` §3 与 `references/anti-bot-protocol.md`：

- 构造搜索 URL（城市代码在 `references/selectors.json`）；
- **优先接口抽取**：设置 `window.__CAREE_PARAMS__` 后运行 `references/extract-list-api.js`（同源 fetch，返回明文薪资 + 公司行业/规模/融资阶段）；
- 接口失败时降级 `references/extract-list.js`（DOM 抽取；注意薪资数字被自定义字体混淆，可能缺失）；
- 每页入库：`python scripts/ingest.py --run <run> --kind jobs --file batch.json --extraction-mode card_only`
- 采集到 `target_count` 即停。

### 阶段 4：详情提取（增强技能分析）

按 playbook §4，对 `state.json.pending_queue` 中的岗位逐条打开详情页，用 `references/extract-detail.js` 抽取后：

```bash
python scripts/ingest.py --run <run> --kind jobs --file detail-batch.json --extraction-mode detail
```

### 阶段 5：背调（可选，按用户选择的范围）

按 `references/background-check.md` 用 Web 搜索采集 Top-N 公司公开信息，入库：

```bash
python scripts/ingest.py --run <run> --kind profile --file profiles-batch.json
```

### 阶段 6：简历访谈与匹配（可选）

调研完成后询问用户是否已有简历（PDF / Word / Markdown / 纯文本 / 粘贴均可）。有则：

```bash
python scripts/extract_resume.py --file "<简历路径>" --out runs/<run>/resume-text.json
# agent 读取文本并写出 runs/<run>/resume.json（结构见 references/resume-matching.md）
python scripts/match.py --run <run> --resume runs/<run>/resume.json
```

### 阶段 7：归一化 + 分析 + 报告 + 导出

```bash
python scripts/normalize.py --run <run>
python scripts/analyze.py   --run <run>
python scripts/report.py    --run <run>
python scripts/export.py    --run <run> --format all
```

完整运行产出 3 个交付物：

1. `<run>/exports/岗位调研汇总.xlsx`：多 sheet（岗位 JD 明细 / 公司与创始人 / 统计分析 / JD 全文速览 / 创始人背景明细 / 简历匹配结果）。
2. `<run>/report.html`：ECharts 图表 + 结论的岗位 seek 报告，金字塔结构。
3. `<run>/resume-match.html`：存在 `match.json` 时自动生成，含匹配排序、差距、建议与冲/稳/保分档。

已有调研工作簿可直接导入：`python scripts/import_xlsx.py --run runs/<id> --xlsx "<path>"`。

## 断点续跑

所有采集 append-only、按 `job_id` 去重；`state.json` 记录阶段与 `pending_queue`。
中断后读取 `state.json`，按 `references/playbook-boss.md` §8 从对应阶段继续。

## 文件地图

| 文件 | 作用 |
|---|---|
| `references/intake-questionnaire.md` | 访谈问题与默认值 |
| `references/browser-contract.md` | 浏览器能力契约与各工具适配 |
| `references/playbook-boss.md` | Boss 检索完整操作手册（核心） |
| `references/anti-bot-protocol.md` | 反风控节奏与暂停协议 |
| `references/selectors.json` | 版本化选择器与城市代码 |
| `references/extract-list.js` / `extract-detail.js` | 页面内抽取脚本 |
| `references/analysis-methods.md` | 月薪口径、分层、技能与 JD、匹配分算法 |
| `references/background-check.md` | 背调查询模板、同名消歧、置信度 |
| `references/resume-matching.md` | 简历提取、结构化字段、匹配算法、匹配报告结构 |
| `references/skill-dictionary.json` | 技能打标词典（可扩展） |
| `templates/report.html` | ECharts 岗位 seek 报告模板 |
| `templates/resume-match.html` | ECharts 简历匹配报告模板 |
| `assets/echarts.min.js` | ECharts 离线包（Apache-2.0，报告内嵌） |
| `scripts/*.py` | preflight/intake/ingest/normalize/analyze/report/export/import_xlsx/extract_resume/match（零第三方依赖） |
| `schema/*.json` | 五类数据结构说明 |

## 宿主兼容性

- **Claude Code**：把整个目录放入 `.claude/skills/` 或作为插件安装。
- **Codex / 其他支持 SKILL.md 约定的 harness**：直接安装；入口沿用本文件。
- **不支持 skill 约定的 harness**：让 agent 阅读本文件作为操作手册，脚本与命令完全一致。
- 浏览器与搜索工具按 `references/browser-contract.md` 做能力映射，不要假设具体工具名。

## 失败处理

| 现象 | 处理 |
|---|---|
| 无浏览器工具 | 停止，给出各候选工具的安装提示 |
| 登录墙反复出现 | 请用户手动登录；不保存凭据 |
| 验证码 / 访问异常 | 立即暂停（playbook §6），用户手动完成后降速恢复 |
| 选择器失效 | 更新 `selectors.json` 与 extract JS（playbook §7），不改脚本 |
| 数据量不足 | 降低结论置信度提示，不建议反复重启刷量 |
| 无 Python | 输出 `winget install Python.Python.3.12` 提示，停止 |
