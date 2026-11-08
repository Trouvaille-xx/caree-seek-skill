# 补充要求与通勤匹配（commute matching）

## 1. 何时启用

只在**用户明确提到通勤/离家近/距离**时启用；默认不询问家庭地址、不调用地图。

- 访谈第 11 题：「还有补充要求吗？比如通勤、薪资、公司类型、排除项。」
- 若回答包含「通勤 / 离家 / 距离 / 地铁 / 开车」等，进入通勤追问：
  1. 家庭或常住地址（小区 / 地铁站 / 商圈均可）
  2. 通勤方式（可多选：地铁 `transit`、公交 `transit`、驾车 `driving`、骑行 `cycling`、步行 `walking`）
  3. 能接受的最长通勤时间（默认 60 分钟）
  4. 是否需要按工作日高峰估算（可选；地图工具支持时使用）
- 若回答包含薪资，合并进 `salary_expect`；其他补充写入 `supplementary_requirements`。

## 2. 地图工具策略（不显性调用）

按以下顺序探测，**使用前必须取得用户明确同意**：

1. **高德地图 MCP（首选）**：国内公交/驾车/步行路线覆盖最好。
2. **百度地图 MCP**：次选；若无高德可用。
3. **Google Maps MCP**：国内覆盖较弱，只作备选。
4. **无可用地图工具**：不要猜通勤时间。引导用户安装高德 MCP（见 §3）；用户拒绝时，把通勤字段标为「未计算」，不纳入匹配。

### 授权话术

- 有工具时：
  > 检测到「高德地图 MCP」。接下来会把你的家庭地址和公司地址发送给高德，用于计算通勤时长；报告只写「方式 + 时间」，不写完整家庭地址。是否允许？
- 工具需要 API Key 时：
  > 高德 MCP 需要高德开放平台的 Web 服务 API Key。请先完成授权/配置；配好后我继续。
- 无工具时：
  > 当前 agent 没有可用的地图工具，无法准确计算通勤。要计算通勤，建议安装高德 MCP；我可以带你配置。若不想安装，本次会把通勤标为「未计算」，不拿它做匹配。

## 3. 高德 MCP 安装指引（按实际 harness 调整）

1. 打开高德开放平台（lbs.amap.com）→ 控制台 → 应用管理 → 创建应用 → 添加 Key，类型选 **Web 服务**。
2. 在 agent 的 MCP 配置中加入高德地图 MCP Server（官方包名以高德文档为准，常见示例）：

```json
{
  "mcpServers": {
    "amap-maps": {
      "command": "npx",
      "args": ["-y", "@amap/amap-maps-mcp-server"],
      "env": { "AMAP_MAPS_API_KEY": "你的 Web 服务 Key" }
    }
  }
}
```

3. 重启/重新加载 agent，确认能调用地理编码与路线规划工具（常见名称：`maps_geo`、`maps_regeocode`、`maps_direction_transit_integrated`、`maps_direction_driving`、`maps_direction_walking`、`maps_distance`）。
4. 用一条真实地址 + 一个公司地址做一次往返测试；结果写回 `commute.json`。

> 隐私：家庭地址只存在本地 run 目录与地图请求中；报告、Excel、匹配卡片只展示通勤方式+时间，不展示完整家庭地址。

## 4. 数据采集流程

1. 运行 `python scripts/commute.py --run <run> --list`，得到 `job_id, title, company, city, district, work_address`。
2. 对每条岗位：
   - 公司地址优先取 JD/公司信息里的工作地址；缺失时用「城市 + 区域」或公司名。
   - 用地图 MCP 地理编码家庭地址与公司地址。
   - 按用户选择的通勤方式逐一算路线；取最短的一种作为该岗位通勤。
   - 记录 `{job_id, mode, minutes, distance_km, status, note}`；`status` 为 `ok|no_route|error`。
3. 把结果写到 `commute.json`（可直接由 agent 生成），再用：

```bash
python scripts/commute.py --run <run> --file commute.json --tool amap-mcp --approved true
```

校验并合并；重复 job_id 保留最短时间。

### commute.json 形态

```json
{
  "generated_at": "2026-11-08T12:00:00+08:00",
  "tool": "amap-mcp",
  "approved": true,
  "home": { "city": "上海", "address": "本地保存，不进入报告" },
  "modes": ["transit", "driving"],
  "max_minutes": 60,
  "entries": [
    { "job_id": "xlsx-0001", "mode": "transit", "minutes": 42, "distance_km": 12.3, "status": "ok", "note": "" }
  ]
}
```

## 5. 匹配评分与推荐口径

### 通勤

- `<= max_minutes`：通勤匹配。
- `<= max_minutes * 1.2 + 10`：略超，标记「可考虑」。
- `<= max_minutes * 1.5`：明显超，标记「可考虑（偏弱）」。
- `> max_minutes * 1.5`：不推荐。
- 未启用 / 无地图数据：标记「未计算」；**不能声称通勤匹配**，整体结论降为「部分/待核实」。

### 薪资（以用户期望下限为准）

设期望月薪下限为 `E`（如 18K）：

- 推荐：岗位上限 `>= E * 0.95` 或岗位中位 `>= E * 0.9`。
- 可考虑：岗位上限 `>= E * 0.85` 或中位 `>= E * 0.8`（略低）。
- 不推荐：低于上述下限。例如 `E=18K` 时，6–12K、12–15K 都不推荐；15–20K、18–20K 可推荐。

### 结果不足时（硬规则）

- 不伪造、不硬凑、不把明显不匹配的岗位包装成推荐。
- 若 0 个「推荐」且 0 个「可考虑」→ 结论 `insufficient`，报告必须明确写：
  - 期望 vs 实际（例如「期望 18K，抓到的岗位月薪上限集中在 12K」）
  - 为什么没有推荐
  - 可行的调整：降薪到 XK、放宽通勤到 Y 分钟、换城市/岗位/行业
  - 原始岗位数据保留在 Excel，标记「不推荐」或「仅供参考」，不得删除或改写数字。
- 若只有 1–4 个推荐或有「可考虑」→ 结论 `partial`，逐条写明「薪资略低」或「通勤略远」。
- 推荐 ≥5 个 → 结论 `ok`。

### 输出字段

- Excel 新增列：**通勤距离**（内容如「地铁 42 分钟」；多方式取最短，可附公里数），**推荐结论**（推荐 / 可考虑 / 待核实 / 不推荐 + 一句话原因）。
- HTML 报告：岗位表新增「通勤」「结论」列；顶部显示推荐结论 banner；结果不足时显示「没有找到符合预期的岗位」与调整建议。
- 简历匹配报告同理；`match.json` 的每条岗位带 `commute` 与 `recommendation_label`。
