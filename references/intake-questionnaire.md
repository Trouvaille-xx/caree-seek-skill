# 意向访谈问卷（intake questionnaire）

在开始检索前，agent 需要和**最终用户**确认求职意向。原则：

- 用自然语言逐条提问即可；若宿主支持结构化选项 UI，可一次多问。
- **12 个问题全部可跳过**；跳过时使用默认值，skill 仍能跑。
- 一次最多问 3–4 个，避免打断；用户说“随便/你来定”就取默认。
- 问完把答案写入 `answers.json`，交给 `intake.py`。

## 问题清单

| # | 问题 | 字段 | 默认 | 跳过语义 |
|---|---|---|---|---|
| 1 | 目标城市？（可多选） | `city` | `[]` | 不限城市 |
| 2 | 工作经验几年？ | `exp_years` | `null` | 不按经验过滤 |
| 3 | 目标岗位关键词？（1–3 个最好） | `role_keywords` | `[]` | 不按岗位过滤，按热度排序 |
| 4 | 目标行业？ | `industry` | `""` | 不限定行业 |
| 5 | 期望月薪区间与薪数？ | `salary_expect` | `null` | 匹配分中薪资项取中性值 |
| 6 | 公司规模偏好？（大厂/中厂/小厂/不限） | `company_size_pref` | `[]` | 不限定 |
| 7 | 岗位阶梯想看哪些？（可多选：同司职级对比 / 跨司对标 / 能力技能地图 / 薪资曲线） | `ladder_modes` | `["same_company","salary_curve"]` | 仅生成这两种 |
| 8 | 公司背调范围？Top-N 深度 / 全量浅摘要 / 手动指定 | `bg_scope` + `top_n` | `top_n` + 5 | 默认对岗位最多的 5 家深度背调 |
| 9 | 输出格式？默认 HTML；是否需要导出 Excel / 飞书 / Markdown？ | `output_format` + `export_targets` | `html` + `[]` | 只出 HTML |
| 10 | 单次抓多少岗位？节奏？（默认 60，上限 100） | `target_count` + `pacing_profile` | 60 + `standard` | 默认值；首次建议 conservative |
| 11 | 还有补充要求吗？（通勤、薪资、公司类型、排除项等） | `supplementary_requirements` | `""` | 无补充要求 |
| 12 | 是否已有简历？PDF / Word / Markdown / 纯文本？ | `resume_path`（流程外） | 无 | 跳过匹配报告，只出岗位报告 + 汇总表；**前两件交付后可再问一次**（见下方） |

### 第 11 题的追问（仅在提到通勤/距离时）

如果用户回答包含「通勤 / 离家近 / 距离 / 地铁 / 开车」：

1. 家庭或常住地址？（小区 / 地铁站 / 商圈均可）
2. 通勤方式？（地铁/公交 = `transit`；驾车 = `driving`；骑行 = `cycling`；步行 = `walking`，可多选）
3. 能接受的最长通勤时间？（默认 60 分钟）

写入 `commute`：

```json
{
  "enabled": true,
  "home_address": "上海·徐汇区·漕河泾",
  "modes": ["transit"],
  "max_minutes": 60
}
```

地图工具的使用必须先取得用户同意；见 `references/commute-matching.md`。若没有可用地图工具，不要猜测通勤时间，标为「未计算」，不纳入匹配。

### 第 12 题的补问（前两件产出后）

如果访谈时用户没有提供简历，**先交付岗位 Excel 与 seek 报告**，再问一次：

> 我可以基于您的简历与刚刚调研的结果为您提供一个投递建议，是否需要？如果需求，请提供简历信息。

用户拒绝或仍不提供 → 不生成匹配报告，不追问、不硬凑。用户同意 → 按 `references/resume-matching.md` 提取并运行 `match.py`，再运行 `report.py` 生成 `resume-match.html`。

## 推荐提问话术

> 在开始前，我想确认几件事（都可以跳过）：
> 1. 你想在哪些城市找？2. 几年经验？3. 目标岗位关键词？
> 4. 什么行业？5. 期望薪资大概多少？6. 偏好大厂还是中小公司？
> 7. 岗位阶梯你最关心：同公司职级对比 / 跨公司对标 / 能力技能地图 / 薪资曲线？（可多选）
> 8. 公司背调：只深挖最相关的 Top-N 家，还是每家给个摘要？
> 9. 报告默认 HTML，需要额外导出 Excel / 飞书表格 / Markdown 吗？
> 10. 这次想抓多少岗位？（默认 60，第一次建议保守一点）
> 11. 还有补充要求吗？比如通勤、薪资、公司类型、排除项？
> 12. 是否已有简历？PDF / Word / 文本都可以，用来做匹配报告。

## answers.json 示例

```json
{
  "city": ["上海"],
  "exp_years": 2,
  "role_keywords": ["AI产品经理", "产品经理"],
  "industry": "互联网/电商",
  "salary_expect": {"min_k": 20, "max_k": 35, "months": 14},
  "company_size_pref": ["大厂", "中厂"],
  "supplementary_requirements": "希望通勤 60 分钟内，优先地铁",
  "commute": {
    "enabled": true,
    "home_address": "上海·徐汇区·漕河泾",
    "modes": ["transit"],
    "max_minutes": 60
  },
  "ladder_modes": ["same_company", "cross_company", "capability_map", "salary_curve"],
  "bg_scope": "top_n",
  "top_n": 5,
  "target_count": 60,
  "output_format": "html",
  "export_targets": ["csv"],
  "pacing_profile": "conservative",
  "questionnaire_answered": ["city", "exp_years", "role_keywords", "industry"]
}
```

写入方式：

```bash
python scripts/intake.py --run runs/<id> --answers answers.json
# 或逐项覆盖
python scripts/intake.py --run runs/<id> --set target_count=60 --set 'city=["上海"]'
```

## 注意事项

- `target_count` 会被收敛到 1–100；超过 100 会提示并截断。
- `ladder_modes` 无效值会被剔除；全空时回退默认。
- `bg_scope=manual` 时，agent 需在背调前让用户点名公司清单。
- 访谈答案会写入报告的头部摘要，方便用户回看本次口径。
