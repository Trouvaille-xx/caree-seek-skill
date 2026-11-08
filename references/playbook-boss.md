# Boss 直聘操作协议（playbook）

本文件是 agent 执行检索的操作手册。所有浏览器动作由 agent 用其浏览器工具完成；
所有数据落盘通过 `scripts/ingest.py`。**禁止自动投递、自动打招呼、自动发消息。**

## 0. 阶段路由

读取 `runs/<run>/state.json` 的 `stage`，按表推进；任何阶段中断后，从这里恢复。

| stage | 下一步 |
|---|---|
| created / intake_done | 运行 preflight，探测浏览器 |
| preflight_done | 登录检测 |
| login_done / collecting | 搜索 + 列表采集，直到 `jobs_collected >= target_count` |
| collecting（仍有 pending_queue） | 详情提取 |
| normalized | 背调富集（可选） |
| profiled / analyzed | 生成报告与导出 |
| reported | 完成 |

## 1. 前置探测

```bash
python scripts/preflight.py
```

按 `references/browser-contract.md` 的优先级实测浏览器工具，选定后回写：

```bash
python scripts/ingest.py --run <run> --state-set active_adapter="ego-browser"
```

无可用浏览器 → 停止并输出安装提示，不要尝试其他抓取手段。

## 2. 登录（一次即可）

1. `navigate` 到 `https://www.zhipin.com`。
2. `read_text`，若命中 `selectors.json → login_wall_patterns`：
   - 截图并告诉用户：「请在浏览器中完成登录（扫码/账号均可），完成后回复‘已登录’。」
   - 等待用户确认，重新 `read_text` 校验；仍为登录墙则再等一轮。
3. 成功：
   ```bash
   python scripts/ingest.py --run <run> --state-set logged_in=true
   ```
4. **不得**要求或保存账号密码；**不得**尝试绕过登录。

## 3. 搜索与列表采集

### 3.1 生成搜索 URL

从 `config.json` 取 `city`、`role_keywords`，从 `selectors.json` 取城市代码：

```
https://www.zhipin.com/web/geek/job?query={keyword}&city={city_code}&page={page}
```

- 城市取第一个匹配项，多个城市逐个关键词轮换；未指定城市用「全国」。
- 关键词一次一个，不要拼接多个词到同一 query。
- 每个关键词默认最多 3 页；总量接近 `target_count` 即停。
- 先 `navigate` 到第 1 页（确认同源与登录态）；后续页优先用接口脚本按 `page` 参数获取，不必逐页跳转。每页之间保持 6–10 秒节奏。

### 3.2 每页流程

1. `navigate` 到搜索 URL（page 从 1 递增），或复用当前搜索页。
2. `read_text`：
   - 命中 `captcha_patterns` → 立即执行 §6 验证码协议。
   - 命中登录墙 → 回到 §2。
   - 页面无结果 → 换关键词或停止。
3. **优先接口抽取（推荐）**：
   - 先设置参数：`window.__CAREE_PARAMS__ = {query:"<关键词>", city:"<城市代码>", page:<页>, pageSize:15}`
   - 再执行 `references/extract-list-api.js`（页面上下文同源 fetch）。
   - 返回明文薪资，并自带公司行业 / 规模 / 融资阶段（`meta` 字段）。
   - 接口失败（非 200、`code != 0`、items 为空）→ 降级 DOM。
4. **DOM 兜底**：`execute_js` 运行 `references/extract-list.js`。
   - 注意：DOM 里的薪资数字由自定义字体渲染，文本不可读；没有接口数据时薪资可能缺失，应标记 `salary_missing`。
   - 两者都返回空 → 按 §7 修复协议排查，不要盲目翻页。
5. 把返回的 `items` 加上元数据后入库：

```json
{
  "search_keyword": "AI产品经理",
  "page": 1,
  "card": { "title": "...", "company": "...", "salary_text": "...", "city": "...", "exp_text": "...", "edu": "...", "tags": [] },
  "meta": { "brand_stage": "D轮", "brand_industry": "人工智能", "brand_scale": "100-499人" },
  "source_url": "https://www.zhipin.com/job_detail/....html"
}
```

保存为 `batch.json` 后：

```bash
python scripts/ingest.py --run <run> --kind jobs --file batch.json --extraction-mode card_only
```

5. 回写页数：
   ```bash
   python scripts/ingest.py --run <run> --pages-done <当前累计页数>
   ```
6. 节奏：按 `references/anti-bot-protocol.md` 休眠（默认 6–10 秒随机）。
7. 若 `jobs_collected >= target_count` → 进入详情阶段（§4）；否则继续下一页/下一个关键词。

## 4. 详情提取

1. 读取 `state.json.pending_queue`（没有详情的 job_id 列表）。
2. 从 `raw/jobs.jsonl` 找出对应 `source_url`。
3. 每批 10 条：
   - `navigate` 到详情页；
   - `execute_js` 运行 `references/extract-detail.js`；
   - 把返回值补上 `job_id` 与 `search_keyword`，合批入库：
     ```bash
     python scripts/ingest.py --run <run> --kind jobs --file detail-batch.json --extraction-mode detail
     ```
   - 每条之间 6–12 秒随机休眠；每批结束休息 60–90 秒。
4. 遇到验证码 → §6；遇到登录墙 → §2。
5. `pending_queue` 清空或达到时间预算 → 进入分析。

> 详情页是可选的增强：列表卡片已含岗位/公司/薪资/城市/经验/学历，详情补充 JD 文本（技能分析依赖它）。

## 5. 归一化、背调、通勤、分析、报告

```bash
python scripts/normalize.py --run <run>
# 启用通勤时：先 --list，等地图 MCP 算完，再 --file 合并
python scripts/commute.py  --run <run> --list
python scripts/commute.py  --run <run> --file commute.json --tool amap-mcp --approved true
python scripts/analyze.py  --run <run>
python scripts/report.py   --run <run>
python scripts/export.py   --run <run> --format all
```

- 背调（可选）：按 `references/background-check.md` 采集公司档案，用 `ingest.py --kind profile` 入库。
- 通勤（可选）：仅在用户主动提出距离要求且授权地图工具后执行，口径见 `references/commute-matching.md`；无工具不猜时长。
- **先交付岗位 Excel + report.html 两件。**
- **简历匹配（可选，后置）**：前两件交付后，如果用户此前没有提供简历，再问一次：
  > 我可以基于您的简历与刚刚调研的结果为您提供一个投递建议，是否需要？如果需求，请提供简历信息。
  同意后按 `references/resume-matching.md` 提取并运行 `match.py`，再运行一次 `report.py` 生成 `resume-match.html`。
- 报告生成后，把 `report.html` / `resume-match.html` / `exports/岗位调研汇总.xlsx` 的路径告诉用户（匹配报告仅在用户提供简历时存在）。
- 已有调研工作簿可直接导入：`python scripts/import_xlsx.py --run <run> --xlsx "<path>"`。

## 6. 验证码暂停协议（硬规则）

1. 立即停止所有后续翻页/打开动作。
2. `screenshot` 保存现场。
3. 告诉用户：「页面出现安全验证，请在浏览器内手动完成（不要把验证码发给任何第三方），完成后回复‘好了’。」
4. 等待用户回复，重新 `read_text` 确认已恢复。
5. 恢复后**降速**：下一条动作前休眠 20–40 秒；把本批剩余量减半。
6. 连续 2 次命中验证码 → 中止本次 run，告诉用户「建议等待 30–60 分钟或隔天再试」，并给出续跑命令：
   ```bash
   python scripts/analyze.py --run <run>   # 已有数据可先出报告
   ```
7. **任何情况下不得**尝试自动过验证码、改指纹、注入 stealth 脚本或使用打码服务。

## 7. 选择器失效修复协议

1. 先判断是否真的失效：页面是否有岗位卡片？`read_text` 是否包含岗位名？
2. 若页面结构变了：
   - `screenshot` + `read_dom` 观察新的类名；
   - 只更新 `references/selectors.json` 与 `extract-list.js`/`extract-detail.js`；
   - 不要修改 Python 脚本；
   - 在 `selectors.json` 的 `updated_at` 记下日期。
3. 修复后先用 1 页验证，再批量继续。

## 8. 断点续跑

- 所有采集都是 append-only；`ingest.py` 按 `job_id` 去重，重复提交不会重复计数。
- 恢复步骤：读 `state.json` → 若 `stage=collecting` 且 `pending_queue` 非空 → 先做详情；否则继续搜索。
- 重复记录通过 `dup_hash` 在分析层识别并报告，不影响主流程。

## 9. 数据交接格式（agent → ingest）

列表卡片记录：

```json
{
  "job_id": "可选，缺省按 source_url 哈希生成",
  "source_url": "https://www.zhipin.com/job_detail/xxx.html",
  "search_keyword": "AI产品经理",
  "page": 1,
  "card": {
    "title": "高级AI产品经理",
    "company": "某公司",
    "salary_text": "25-40K·14薪",
    "city": "上海·浦东新区",
    "exp_text": "3-5年",
    "edu": "本科",
    "tags": ["B端产品", "大模型"]
  }
}
```

详情记录：在上面的基础上加：

```json
{
  "detail": {
    "raw_text": "岗位职责：……",
    "posted_at": "2026-11-01",
    "benefits": ["五险一金", "弹性工作"]
  }
}
```

公司档案记录（背调）：

```json
{
  "display_name": "某公司",
  "company_key": "可选，缺省自动生成",
  "tier": "tier1|tier2|tier3|unknown",
  "funding_stage": "B 轮",
  "size": "100-499人",
  "industry": "企业服务",
  "founded": "2019",
  "recent_news": [{"headline": "...", "date": "2026-09-01"}],
  "risk_signals": ["欠薪爆料（未核实）"],
  "sources": [{"title": "官网", "url": "https://...", "date": "2026-10-01"}],
  "confidence": "high|med|low",
  "disambiguation_note": "同名公司较多，未完全确认主体"
}
```
