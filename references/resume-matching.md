# 简历 × 岗位匹配（resume matching）

在岗位调研与分析完成后执行。产出**独立**的 HTML 匹配报告，并写入汇总 Excel 的「简历匹配结果」sheet。

## 1. 时机

主报告（seek 报告）已生成，或至少 `normalized/jobs.json` 与 `analysis.json` 已就绪后，询问用户：

> 你已经有简历了吗？如果有，我可以基于简历做岗位匹配、差距分析和投递建议，并单独生成一份匹配报告。

- 没有 → 跳过，只交付岗位报告 + 汇总表。
- 有 → 支持 PDF / Word(.docx) / Markdown / 纯文本，或让用户直接粘贴。

## 2. 提取文本

```bash
# PDF / DOCX / TXT / MD
python scripts/extract_resume.py --file "C:/path/resume.pdf" --out runs/<run>/resume-text.json

# 用户直接粘贴
python scripts/extract_resume.py --text-file pasted.txt --out runs/<run>/resume-text.json
```

PDF 解析依赖 `pypdf` / `PyPDF2` / `pdftotext` 之一。若都不存在：
- 让宿主 agent 用其文件读取能力直接读 PDF；
- 把文本写入 `.txt` 后用 `--text-file`；
- 或让用户粘贴简历文本。

## 3. 结构化简历（agent 完成）

agent 读取 `resume-text.json` 后，写出 `runs/<run>/resume.json`：

```json
{
  "text": "简历原文……",
  "profile": {
    "name": "张三",
    "years_experience": 3,
    "education": "本科",
    "city": "上海",
    "expected_salary": { "min_k": 20, "max_k": 30 },
    "skills": ["大模型", "RAG", "Agent/智能体", "Prompt", "需求分析", "PRD", "数据分析", "SQL"],
    "titles": ["AI产品经理", "大模型产品经理"],
    "industries": ["互联网", "电商"],
    "strengths": ["从 0 到 1 落地过 RAG 知识库"],
    "projects": [
      { "name": "企业知识库 Agent", "summary": "负责需求、评测与上线，问答准确率从 62% 提升到 84%" }
    ]
  }
}
```

字段缺失时，`match.py` 会从 `text` 里自动推断年限、学历、城市、期望薪资、技能与方向。

## 4. 匹配算法

```bash
python scripts/match.py --run <run> --resume runs/<run>/resume.json
```

总分 100：

| 维度 | 分值 | 规则 |
|---|---|---|
| 技能覆盖 | 40 | 岗位要求的技能中，简历已具备的比例 |
| 经验契合 | 20 | 落在要求区间满分；略低降档；明显高于上限降档；校招岗对资深候选人降档 |
| 学历 | 10 | 满足要求 10，不满足 4 |
| 薪资契合 | 15 | 岗位月薪中位与期望月薪中值的相对偏差 |
| 城市 | 5 | 城市匹配 5，未填 2.5 |
| 方向 | 10 | 简历目标方向与岗位标题的重合度 |

输出 `runs/<run>/match.json`：排名、命中/缺失技能、分维度得分、匹配说明、技能缺口、薪资缺口、冲/稳/保分档、雷达数据、建议。

## 5. 生成报告

```bash
python scripts/report.py --run <run>
```

会同时生成：
- `report.html`：岗位 seek 报告
- `resume-match.html`：简历匹配报告（存在 `match.json` 时）

匹配报告结构：
1. 匹配总览（最佳匹配、平均分、期望 vs 中位、冲/稳/保数量）
2. 匹配质量：最佳匹配仪表盘、技能雷达、Top 10 匹配分、薪资×匹配分散点、投递分档环图、技能缺口
3. 投递策略：冲 / 稳 / 保三档清单
4. 匹配岗位明细（命中/缺失技能 + 匹配说明）
5. 简历优化建议（技能缺口、薪资预期、投递节奏、关键词前置）
6. 方法与合规

## 6. 边界

- 匹配分是启发式，不替代面试判断。
- 简历信息只用于本地匹配，不上传第三方。
- 不虚构简历中没有的经历；建议只能基于已有事实改写。
- 报告中的薪资为岗位挂牌价，非 offer 成交价。
