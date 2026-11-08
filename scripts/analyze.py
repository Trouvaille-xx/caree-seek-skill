"""分析：月薪口径的薪资结构、分层驱动、技能溢价、JD 特征、公司与阶梯。纯计算，不联网。"""
from __future__ import annotations

import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

LEVEL_ORDER = ["初级", "中级", "高级", "资深", "专家", "管理"]
EXP_ORDER = ["1-3年", "经验不限", "在校/应届", "3-5年", "5-10年", "10年以上", "未标注"]
FUNDING_ORDER = ["未融资", "天使轮", "A轮", "B轮", "C轮", "D轮及以上", "已上市", "不需要融资", "未披露"]
SIZE_ORDER = ["0-20人", "20-99人", "100-499人", "500-999人", "1000-9999人", "10000人以上", "未披露"]

# 固定 10 箱，与参考报告口径一致；空箱不输出
HIST_EDGES = [
    (0, 10, "<10K"), (10, 15, "10–15K"), (15, 20, "15–20K"), (20, 25, "20–25K"),
    (25, 30, "25–30K"), (30, 35, "30–35K"), (35, 40, "35–40K"),
    (40, 50, "40–50K"), (50, 60, "50–60K"), (60, None, "60K+"),
]
JD_EDGES = [(0, 400, "<400字"), (400, 700, "400–700字"), (700, 1000, "700–1000字"),
            (1000, 1500, "1000–1500字"), (1500, None, "1500字+")]

TITLE_GROUPS = [
    ("AI产品经理", ["ai产品经理", "ai 产品经理", "ai产品", "人工智能产品"]),
    ("大模型", ["大模型", "llm"]),
    ("AIGC", ["aigc", "生成式"]),
    ("数据产品", ["数据产品"]),
    ("策略产品", ["策略产品"]),
    ("智能产品", ["智能产品"]),
    ("算法产品", ["算法产品"]),
]

# 词云：标题切词 + 技能标签；同一岗位内同一关键词只计一次
TITLE_SPLIT_RE = re.compile(r"[（）()【】\[\]/、,，·|&+\-—_\s]+")
TITLE_SUFFIX_RE = re.compile(r"(方向|岗位|职位)$")
TITLE_NOISE = {
    "全职", "实习", "实习生", "急聘", "双休", "五险一金", "岗位", "职位", "方向",
    "工程师", "专员", "助理", "高级", "资深", "初级", "中级", "专家", "负责人",
    "总监", "组长", "经理", "产品", "leader", "head",
}
ACRONYM = {
    "ai": "AI", "aigc": "AIGC", "rag": "RAG", "agent": "Agent", "prompt": "Prompt",
    "saas": "SaaS", "nlp": "NLP", "api": "API", "prd": "PRD", "sql": "SQL",
    "geo": "GEO", "fde": "FDE", "llm": "LLM", "b端": "B端", "c端": "C端",
    "b2b": "B2B", "b2c": "B2C", "tob": "ToB", "toc": "ToC",
}

# ---------- 公司调研 / 老板团队评分 ----------
FUNDING_EXACT = {
    "未融资", "不需要融资", "天使轮", "种子轮", "Pre-A轮", "Pre-B轮", "A轮", "A+轮",
    "B轮", "B+轮", "C轮", "C+轮", "D轮", "D轮及以上", "战略融资", "已上市", "IPO",
}

TOP_COMPANY_GROUPS = [
    ("阿里巴巴", ["阿里巴巴", "阿里"]), ("腾讯", ["腾讯"]), ("字节跳动", ["字节跳动", "字节"]),
    ("百度", ["百度"]), ("美团", ["美团"]), ("京东", ["京东"]), ("网易", ["网易"]),
    ("华为", ["华为"]), ("小米", ["小米"]), ("滴滴", ["滴滴"]), ("快手", ["快手"]),
    ("拼多多", ["拼多多"]), ("蚂蚁集团", ["蚂蚁集团", "蚂蚁金服"]), ("微软", ["微软"]),
    ("谷歌", ["谷歌", "google"]), ("亚马逊", ["亚马逊", "amazon"]), ("苹果", ["苹果公司", "apple"]),
    ("Meta", ["meta", "facebook"]), ("英特尔", ["英特尔", "intel"]), ("英伟达", ["英伟达", "nvidia"]),
    ("台积电", ["台积电"]), ("三星", ["三星"]), ("思科", ["思科", "cisco"]),
    ("甲骨文", ["甲骨文", "oracle"]), ("SAP", ["sap"]), ("IBM", ["ibm"]),
    ("埃森哲", ["埃森哲", "accenture"]), ("麦肯锡", ["麦肯锡", "mckinsey"]),
    ("贝恩", ["贝恩", "bain"]), ("BCG", ["bcg", "波士顿咨询"]), ("高盛", ["高盛", "goldman"]),
    ("摩根士丹利", ["摩根士丹利", "morgan stanley"]), ("摩根大通", ["摩根大通", "jpmorgan"]),
    ("红杉", ["红杉", "sequoia"]), ("IDG", ["idg"]), ("经纬", ["经纬"]),
    ("真格", ["真格"]), ("创新工场", ["创新工场"]), ("金山", ["金山软件", "金山"]),
    ("猎豹移动", ["猎豹移动", "猎豹"]), ("携程", ["携程"]), ("去哪儿", ["去哪儿"]),
    ("新浪", ["新浪"]), ("搜狐", ["搜狐"]), ("用友", ["用友"]), ("金蝶", ["金蝶"]),
    ("中兴", ["中兴"]), ("大疆", ["大疆", "dji"]), ("商汤", ["商汤"]), ("旷视", ["旷视"]),
    ("科大讯飞", ["科大讯飞", "讯飞"]), ("海康威视", ["海康威视", "海康"]),
    ("浪潮", ["浪潮"]), ("西门子", ["西门子", "siemens"]), ("博世", ["博世", "bosch"]),
    ("飞利浦", ["飞利浦", "philips"]), ("宝洁", ["宝洁", "p&g"]),
    ("联合利华", ["联合利华", "unilever"]), ("麦格纳", ["麦格纳", "magna"]),
    ("博格华纳", ["博格华纳", "borgwarner"]), ("法雷奥", ["法雷奥", "valeo"]),
    ("山特维克", ["山特维克", "sandvik"]),
    ("美卓", ["美卓", "metso"]), ("贝赛默", ["贝赛默", "bessemer"]),
    ("大陆集团", ["大陆集团", "continental ag"]),
]

TOP_SCHOOL_GROUPS = [
    ("清华大学", ["清华大学", "清华"]), ("北京大学", ["北京大学", "北大"]),
    ("复旦大学", ["复旦大学", "复旦"]), ("上海交通大学", ["上海交通大学", "上海交大"]),
    ("浙江大学", ["浙江大学", "浙大"]), ("中国科学技术大学", ["中国科学技术大学", "中科大"]),
    ("南京大学", ["南京大学"]), ("哈尔滨工业大学", ["哈尔滨工业大学", "哈工大"]),
    ("中国人民大学", ["中国人民大学"]), ("香港大学", ["香港大学", "港大"]),
    ("香港中文大学", ["香港中文大学", "港中文"]), ("香港科技大学", ["香港科技大学", "港科大"]),
    ("斯坦福大学", ["斯坦福", "stanford"]), ("哈佛大学", ["哈佛", "harvard"]),
    ("麻省理工学院", ["麻省理工"]), ("加州大学伯克利分校", ["加州大学伯克利", "伯克利", "berkeley"]),
    ("卡内基梅隆大学", ["卡内基梅隆", "cmu"]), ("牛津大学", ["牛津", "oxford"]),
    ("剑桥大学", ["剑桥", "cambridge"]), ("耶鲁大学", ["耶鲁", "yale"]),
    ("普林斯顿大学", ["普林斯顿", "princeton"]), ("哥伦比亚大学", ["哥伦比亚大学", "哥大", "columbia"]),
    ("宾夕法尼亚大学沃顿商学院", ["沃顿", "wharton"]), ("伦敦政治经济学院", ["伦敦政经"]),
    ("帝国理工学院", ["帝国理工", "imperial college"]), ("新加坡国立大学", ["新加坡国立"]),
    ("南洋理工大学", ["南洋理工"]), ("北京邮电大学", ["北京邮电大学", "北邮"]),
    ("同济大学", ["同济大学", "同济"]), ("武汉大学", ["武汉大学", "武大"]),
    ("华中科技大学", ["华中科技大学", "华科"]), ("西安交通大学", ["西安交通大学", "西安交大"]),
    ("中山大学", ["中山大学"]), ("北京航空航天大学", ["北京航空航天大学", "北航"]),
    ("北京理工大学", ["北京理工大学", "北理工"]), ("电子科技大学", ["电子科技大学", "电子科大"]),
]

ROLE_GROUPS = [
    ("创始人", ["创始人", "联合创始人", "创办人", "co-founder", "founder"]),
    ("CEO/总裁", ["ceo", "首席执行官", "总裁", "总经理"]),
    ("CTO/技术负责人", ["cto", "首席技术官", "技术总监", "技术负责人"]),
    ("COO/运营负责人", ["coo", "首席运营官", "运营总监"]),
    ("CFO/财务负责人", ["cfo", "首席财务官", "财务总监"]),
    ("董事长/董事", ["董事长", "董事"]),
    ("副总裁/VP", ["副总裁", "vice president", " vp "]),
    ("合伙人", ["合伙人", "partner"]),
    ("总监/负责人", ["总监", "负责人", "head of"]),
    ("教授/研究员", ["教授", "研究员", "院长"]),
]

ADVANCED_GROUPS = [
    ("博士", ["博士", "phd"]), ("硕士/MBA", ["硕士", "mba", "emba", "研究生"]),
    ("海归/海外", ["海归", "留学", "海外", "硅谷", "华尔街"]),
    ("连续创业", ["连续创业", "二次创业", "再次创业"]),
    ("上市公司/世界500强", ["上市公司", "世界500强", "财富500强", "独角兽"]),
]

FAMOUS_PEOPLE = ["雷军", "马云", "马化腾", "李彦宏", "张一鸣", "王兴", "黄峥", "刘强东",
                 "丁磊", "任正非", "傅盛", "李开复", "徐小平", "沈南鹏"]

SALARY_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[kK]?\s*[-~—]\s*(\d+(?:\.\d+)?)\s*[kK]?")
LEGAL_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|集团|控股|科技|技术|网络|信息|服务|"
    r"中国|北京|上海|深圳|杭州|广州|成都|南京|武汉|西安|苏州|天津)"
)


def percentile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return round(float(s[0]), 1)
    idx = (len(s) - 1) * q
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return round(s[lo] * (1 - frac) + s[hi] * frac, 1)


def dist_stats(vals):
    if not vals:
        return {"n": 0, "min": None, "p25": None, "p50": None, "p75": None, "max": None, "mean": None}
    return {
        "n": len(vals),
        "min": round(float(min(vals)), 1),
        "p25": percentile(vals, 0.25),
        "p50": percentile(vals, 0.5),
        "p75": percentile(vals, 0.75),
        "max": round(float(max(vals)), 1),
        "mean": round(sum(vals) / len(vals), 1),
    }


def monthly_mid(job):
    sal = job.get("salary") or {}
    if sal.get("mid_k") is not None:
        return sal["mid_k"]
    if sal.get("mid_annual_k") is not None and sal.get("months"):
        return round(sal["mid_annual_k"] / sal["months"], 2)
    return None


def salary_width(job):
    sal = job.get("salary") or {}
    if sal.get("width_k") is not None:
        return sal["width_k"]
    if sal.get("min_k") is not None and sal.get("max_k") is not None:
        return round(sal["max_k"] - sal["min_k"], 2)
    return None


def histogram_fixed(vals):
    out = []
    for lo, hi, label in HIST_EDGES:
        count = sum(1 for v in vals if v >= lo and (hi is None or v < hi))
        if count:
            out.append({"label": label, "lo": lo, "hi": hi, "count": count})
    return out


def nice_step(span, target=10):
    if span <= 0:
        return 1.0
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if raw <= mult * mag:
            return mult * mag
    return 10 * mag


def annual_bin_label(lo, hi):
    def wan(value):
        value = value / 10.0  # K -> 万
        if value >= 100:
            return f"{value:.0f}"
        text = f"{value:.1f}"
        return text.rstrip("0").rstrip(".") if "." in text else text
    if hi <= lo:
        return f"{wan(lo)}万"
    return f"{wan(lo)}–{wan(hi)}万"


def histogram_annual(vals, target=10):
    """折算年薪（K/年）自适应分箱：按数据跨度选整齐的步长，空箱不输出。"""
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return [{"label": annual_bin_label(lo, lo), "lo": round(float(lo), 1),
                 "hi": round(float(hi), 1), "count": len(vals)}]
    step = nice_step(hi - lo, target)
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    bins = max(1, int(round((end - start) / step)))
    out = []
    for i in range(bins):
        a = start + i * step
        b = a + step
        count = sum(1 for v in vals if (a <= v < b) or (i == bins - 1 and v == b))
        if count:
            label = annual_bin_label(a, b)
            if i == 0 and a == 0:
                label = "≤" + annual_bin_label(0, b).split("–", 1)[-1]
            out.append({"label": label, "lo": round(a, 1),
                        "hi": round(b, 1), "count": count})
    return out


def template_range(text):
    t = (text or "").replace("千", "K").strip()
    if not t or "面议" in t:
        return None
    m = SALARY_RANGE_RE.search(t)
    if not m:
        return None
    if "元" in t and "K" not in t:
        return float(m.group(1)) / 1000.0, float(m.group(2)) / 1000.0
    return float(m.group(1)), float(m.group(2))


def salary_templates(jobs):
    counter = Counter()
    for job in jobs:
        text = (job.get("salary") or {}).get("text") or ""
        if text:
            counter[text] += 1
    out = []
    for text, count in counter.most_common(15):
        rng = template_range(text)
        if not rng:
            continue
        out.append({"text": text, "lo": rng[0], "hi": rng[1], "count": count})
    return out


def exp_bucket(job):
    exp = job.get("exp") or {}
    emin, emax = exp.get("min"), exp.get("max")
    if emin is None:
        return "未标注"
    if emin == 0 and (emax is None or emax >= 99):
        return "经验不限"
    if emin == 0 and emax is not None and emax <= 1:
        return "在校/应届"
    if emin <= 3 and emax is not None and emax <= 3:
        return "1-3年"
    if emax is None or emax >= 99:
        return f"{emin}年以上"
    return f"{emin}-{emax}年"


def scope_bucket(job):
    bucket = exp_bucket(job)
    if bucket == "1-3年":
        return "核心(1-3年)"
    if bucket in ("经验不限", "在校/应届"):
        return "扩展(经验不限/应届)"
    return "其他"


def funding_label(raw):
    s = (raw or "").strip()
    if not s:
        return "未披露"
    if "上市" in s:
        return "已上市"
    if "不需要融资" in s:
        return "不需要融资"
    if "未融资" in s:
        return "未融资"
    for key in ["天使轮", "A轮", "B轮", "C轮", "D轮及以上"]:
        if key in s:
            return key
    return s


def is_funding_text(text):
    s = str(text or "").strip()
    if not s:
        return False
    if s in FUNDING_EXACT:
        return True
    if "轮" in s and len(s) <= 8:
        return True
    return any(token in s for token in ("未融资", "不需要融资", "战略融资"))


def funding_from(profile, meta):
    extras = (profile or {}).get("extras") or {}
    for candidate in [
        (meta or {}).get("stage"), (profile or {}).get("funding_stage"),
        extras.get("融资阶段"), (profile or {}).get("industry"),
        (meta or {}).get("industry"), extras.get("行业"),
    ]:
        if candidate and is_funding_text(candidate):
            return funding_label(candidate)
    return "未披露"


def industry_from(profile, meta):
    extras = (profile or {}).get("extras") or {}
    for candidate in [
        (meta or {}).get("industry"), (profile or {}).get("industry"), extras.get("行业"),
    ]:
        if candidate and not is_funding_text(candidate):
            return str(candidate).strip()
    return "未披露"


def parse_founded_year(profile, meta):
    extras = (profile or {}).get("extras") or {}
    for candidate in [(profile or {}).get("founded"), extras.get("成立日期"), (meta or {}).get("founded")]:
        match = re.search(r"(19|20)\d{2}", str(candidate or ""))
        if match:
            return int(match.group(0))
    return None


def company_age_bucket(year):
    if not year:
        return "未披露"
    age = max(0, date.today().year - year)
    if age <= 3:
        return "≤3年"
    if age <= 5:
        return "3–5年"
    if age <= 10:
        return "5–10年"
    if age <= 20:
        return "10–20年"
    return "20年+"


def _match_groups(text, groups):
    lowered = str(text or "").lower()
    hits = []
    for display, aliases in groups:
        if any(alias.lower() in lowered for alias in aliases):
            hits.append(display)
    return hits


def team_background_score(profile):
    """老板/团队背景评分：名企、名校、高管创业、学历海外、知名人物 + 置信度。"""
    profile = profile or {}
    founder = profile.get("founder") or {}
    extras = profile.get("extras") or {}
    text = " ".join(str(x) for x in [
        founder.get("name"), founder.get("background"), extras.get("创始人"),
        extras.get("联合创始人"), extras.get("创始人背景"), extras.get("法定代表人"),
    ] if x).strip()
    if not text:
        return {"score": None, "label": "未评估", "signals": [], "confidence": "none"}

    companies = _match_groups(text, TOP_COMPANY_GROUPS)
    schools = _match_groups(text, TOP_SCHOOL_GROUPS)
    roles = _match_groups(text, ROLE_GROUPS)
    advanced = _match_groups(text, ADVANCED_GROUPS)
    famous = [name for name in FAMOUS_PEOPLE if name in text]
    score = 44
    signals = []
    if companies:
        score += min(30, 10 * len(companies))
        signals.append("名企：" + "、".join(companies[:4]))
    if schools:
        score += min(24, 12 * len(schools))
        signals.append("高校：" + "、".join(schools[:4]))
    if roles:
        score += min(18, 6 * len(roles))
        signals.append("高管/创业：" + "、".join(roles[:4]))
    if advanced:
        score += min(15, 5 * len(advanced))
        signals.append("学历/经历：" + "、".join(advanced[:4]))
    if famous:
        score += min(12, 6 * len(famous))
        signals.append("知名人物：" + "、".join(famous[:3]))
    confidence = founder.get("confidence") or profile.get("confidence") or "low"
    score += {"high": 10, "med": 5}.get(confidence, 0)
    score = max(0, min(100, round(score)))
    if score >= 80:
        label = "强"
    elif score >= 60:
        label = "较好"
    elif score >= 45:
        label = "一般"
    else:
        label = "有限"
    return {"score": score, "label": label, "signals": signals, "confidence": confidence}


def desensitized_label(job):
    raw = str((job.get("extras") or {}).get("是否脱敏") or "").strip()
    if raw in ("是", "否"):
        return raw
    name = job.get("company") or ""
    return "是" if ("某" in name and "公司" in name) else "否"


def group_stats(jobs, key_fn, order=None):
    groups = defaultdict(list)
    for job in jobs:
        mid = monthly_mid(job)
        if mid is None:
            continue
        groups[key_fn(job)].append(mid)
    items = [(label, dist_stats(vals)) for label, vals in groups.items()]
    if order:
        index = {label: i for i, label in enumerate(order)}
        items.sort(key=lambda kv: (index.get(kv[0], 999), -kv[1]["n"]))
    else:
        items.sort(key=lambda kv: -kv[1]["n"])
    return [{"label": label, **stats} for label, stats in items]


def pearson(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else None


def load_profiles(run: Path) -> dict:
    profiles = {}
    for path in sorted((run / "profiles").glob("*.json")):
        data = c.read_json(path, {}) or {}
        profiles[data.get("company_key") or path.stem] = data
    return profiles


def load_builtin_tiers() -> dict:
    data = c.read_json(c.ROOT / "references" / "company-tiers.json", {}) or {}
    return data.get("companies", {}) or {}


def builtin_tier(company: str, tiers: dict):
    if not company or not tiers:
        return None
    if company in tiers:
        return tiers[company]
    stripped = LEGAL_SUFFIX_RE.sub("", company)
    if stripped in tiers:
        return tiers[stripped]
    for known in sorted(tiers, key=len, reverse=True):
        if known and (known in company or stripped.startswith(known)):
            return tiers[known]
    return None


def match_score(job, cfg, profile):
    score = 0.0
    keywords = [str(k).lower() for k in cfg.get("role_keywords", []) if k]
    text = " ".join([job.get("title", ""), job.get("title_family", ""), job.get("jd_summary", ""),
                     " ".join(job.get("skills", []))]).lower()
    if keywords:
        score += 40.0 * sum(1 for k in keywords if k in text) / len(keywords)
    else:
        score += 20.0

    se = cfg.get("salary_expect") or {}
    lo, hi = se.get("min_k"), se.get("max_k")
    mid = monthly_mid(job)
    if lo and hi and mid:
        expect_mid = (float(lo) + float(hi)) / 2.0
        diff = abs(mid - expect_mid) / expect_mid if expect_mid else 1.0
        score += 25.0 * max(0.0, 1.0 - min(diff, 1.0))
    else:
        score += 12.5

    cities = cfg.get("city") or []
    if cities:
        if job.get("city") in cities:
            score += 15.0
    else:
        score += 10.0

    years = cfg.get("exp_years")
    exp = job.get("exp") or {}
    emin, emax = exp.get("min"), exp.get("max")
    if years is not None and emin is not None:
        if emin <= years <= (emax if emax is not None else 99):
            score += 10.0
        elif emin - 1 <= years <= (emax if emax is not None else 99) + 1:
            score += 6.0
        else:
            score += 2.0
    else:
        score += 5.0

    conf = (profile or {}).get("confidence")
    score += {"high": 10.0, "med": 7.0, "low": 4.0}.get(conf, 5.0)
    return round(min(100.0, score), 1)


def same_company_ladder(jobs, profiles):
    grouped = defaultdict(lambda: defaultdict(list))
    for job in jobs:
        level = job.get("level_guess")
        if level in LEVEL_ORDER:
            grouped[job["company_key"]][level].append(job)
    blocks = []
    for company_key, levels in grouped.items():
        rows = []
        for level in LEVEL_ORDER:
            items = levels.get(level) or []
            if not items:
                continue
            vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
            rows.append({"level": level, "n": len(items), "median": percentile(vals, 0.5),
                         "titles": sorted({x["title"] for x in items})[:4]})
        if len(rows) < 2:
            continue
        prev = None
        for row in rows:
            row["step_pct"] = round((row["median"] - prev) / prev * 100, 1) if row["median"] is not None and prev else None
            if row["median"] is not None:
                prev = row["median"]
        total = sum(row["n"] for row in rows)
        display = (profiles.get(company_key) or {}).get("display_name") or next(
            (x["company"] for x in jobs if x["company_key"] == company_key), company_key)
        blocks.append({"company_key": company_key, "company": display, "rows": rows, "n": total,
                       "confidence": "ok" if len(rows) >= 3 and total >= 6 else "low"})
    blocks.sort(key=lambda b: -b["n"])
    return blocks


def cross_company_matrix(jobs, profiles, max_companies=12):
    counts = Counter(job["company_key"] for job in jobs)
    keys = [key for key, _ in counts.most_common(max_companies)]
    levels = [level for level in LEVEL_ORDER if any(job.get("level_guess") == level for job in jobs)]
    rows = []
    for company_key in keys:
        buckets = defaultdict(list)
        company_name = ""
        for job in jobs:
            if job["company_key"] != company_key:
                continue
            company_name = company_name or job["company"]
            if job.get("level_guess") in levels:
                buckets[job["level_guess"]].append(job)
        if not buckets:
            continue
        cells = {}
        for level, items in buckets.items():
            vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
            cells[level] = {"n": len(items), "median": percentile(vals, 0.5)}
        rows.append({"company_key": company_key,
                     "company": (profiles.get(company_key) or {}).get("display_name") or company_name,
                     "cells": cells})
    rows.sort(key=lambda r: -sum(cell["n"] for cell in r["cells"].values()))
    return {"levels": levels, "rows": rows}


def capability_map(jobs, base_median):
    per_skill = defaultdict(list)
    for job in jobs:
        for skill in job.get("skills", []):
            per_skill[skill].append(job)
    total = len(jobs) or 1
    rows = []
    for skill, items in per_skill.items():
        if len(items) < 3:
            continue
        vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
        if not vals:
            continue
        median = percentile(vals, 0.5)
        level_dist = Counter(x.get("level_guess") for x in items)
        rows.append({"skill": skill, "n": len(items), "coverage_pct": round(len(items) / total * 100, 1),
                     "median": median, "lift": round(median - (base_median or 0), 1),
                     "levels": [lvl for lvl, _ in level_dist.most_common(3) if lvl and lvl != "未知"]})
    rows.sort(key=lambda r: (-(max(r["lift"], 0) * r["coverage_pct"]), -r["n"]))
    return rows


def salary_curve(jobs):
    buckets = [(0, 1, "0-1年"), (1, 3, "1-3年"), (3, 5, "3-5年"), (5, 8, "5-8年"), (8, 99, "8年+")]
    rows = []
    for lo, hi, label in buckets:
        vals = []
        for job in jobs:
            years = (job.get("exp") or {}).get("min")
            mid = monthly_mid(job)
            if years is None or mid is None:
                continue
            if lo <= years < hi:
                vals.append(mid)
        if vals:
            rows.append({"bucket": label, "n": len(vals), "p25": percentile(vals, 0.25),
                         "median": percentile(vals, 0.5), "p75": percentile(vals, 0.75)})
    return rows


def prettify_keyword(key: str) -> str:
    for token, display in ACRONYM.items():
        if key.startswith(token):
            return display + key[len(token):]
    return key


def keyword_cloud(jobs, max_items=50):
    counts = Counter()
    displays = {}
    for job in jobs:
        terms = set()
        title = re.sub(r"\s+", "", job.get("title") or "")
        if title:
            for part in TITLE_SPLIT_RE.split(title):
                token = TITLE_SUFFIX_RE.sub("", part.strip().lower())
                if 2 <= len(token) <= 16 and token not in TITLE_NOISE:
                    terms.add(token)
        for skill in job.get("skills") or []:
            token = str(skill).strip().lower()
            if 2 <= len(token) <= 20:
                terms.add(token)
        for token in terms:
            counts[token] += 1
    for job in jobs:
        for skill in job.get("skills") or []:
            token = str(skill).strip().lower()
            if token in counts:
                displays[token] = str(skill).strip()
    items = [(token, count) for token, count in counts.items() if count >= 2]
    if not items:
        items = list(counts.items())
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    return [{"text": displays.get(token) or prettify_keyword(token), "count": count}
            for token, count in items[:max_items]]


def title_stats(jobs):
    out = []
    for label, aliases in TITLE_GROUPS:
        hits = [j for j in jobs if any(a in (j.get("title") or "").lower() for a in aliases)]
        vals = [monthly_mid(j) for j in hits if monthly_mid(j) is not None]
        if hits:
            st = dist_stats(vals)
            out.append({"label": label, "n": len(hits), "p50": st["p50"], "p75": st["p75"]})
    return out


def skill_combos(jobs, base_median, max_items=10):
    """技能共现组合：同一岗位出现的两个技能，按岗位数排序。"""
    pair_counts = Counter()
    pair_jobs = defaultdict(list)
    for job in jobs:
        skills = sorted({str(s).strip() for s in (job.get("skills") or []) if str(s).strip()})
        for i in range(len(skills)):
            for j in range(i + 1, len(skills)):
                pair = (skills[i], skills[j])
                pair_counts[pair] += 1
                pair_jobs[pair].append(job)
    rows = []
    for pair, count in pair_counts.most_common(60):
        if count < 3:
            continue
        vals = [monthly_mid(x) for x in pair_jobs[pair] if monthly_mid(x) is not None]
        if not vals:
            continue
        median = percentile(vals, 0.5)
        rows.append({"a": pair[0], "b": pair[1], "n": count, "median": median,
                     "lift": round(median - (base_median or 0), 1)})
    rows.sort(key=lambda r: (-r["n"], -max(r["lift"], 0)))
    return rows[:max_items]


def skill_stats(jobs, base_median):
    total = len(jobs) or 1
    per_skill = defaultdict(list)
    for job in jobs:
        for skill in job.get("skills", []):
            per_skill[skill].append(job)
    top = []
    for skill, items in per_skill.items():
        vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
        if not vals:
            continue
        median = percentile(vals, 0.5)
        top.append({"skill": skill, "n": len(items), "pct": round(len(items) / total * 100, 1),
                    "median": median, "lift": round(median - (base_median or 0), 1)})
    top.sort(key=lambda x: -x["n"])
    lift = [x for x in top if x["n"] >= 5]
    lift.sort(key=lambda x: (-x["lift"], -x["n"]))
    entry = [x for x in top if x["n"] >= 10 and x["lift"] <= 1.0]
    entry.sort(key=lambda x: -x["n"])
    return {"top": top[:20], "lift": lift[:15], "entry": entry[:8],
            "combos": skill_combos(jobs, base_median)}


def jd_stats(jobs):
    lengths = []
    pairs = []
    for job in jobs:
        length = job.get("jd_length") or len(re.sub(r"\s+", "", job.get("jd_text") or ""))
        if length:
            lengths.append(length)
        mid = monthly_mid(job)
        if length and mid is not None:
            pairs.append((length, mid))
    corr = pearson([a for a, _ in pairs], [b for _, b in pairs])
    hist = []
    for lo, hi, label in JD_EDGES:
        count = sum(1 for x in lengths if x >= lo and (hi is None or x < hi))
        if count:
            hist.append({"label": label, "count": count})
    st = dist_stats(lengths)
    return {"n": st["n"], "min": st["min"], "p25": st["p25"], "p50": st["p50"],
            "p75": st["p75"], "max": st["max"],
            "corr_salary": round(corr, 3) if corr is not None else None, "histogram": hist}


def founder_stats(profiles, company_index=None):
    confidence = Counter()
    with_name = 0
    for profile in profiles.values():
        if (profile.get("founder") or {}).get("name"):
            with_name += 1
        confidence[profile.get("confidence") or "low"] += 1
    team_score = Counter()
    for entry in (company_index or {}).values():
        team_score[(entry.get("team_score") or {}).get("label") or "未评估"] += 1
    return {"companies": len(profiles), "with_founder": with_name,
            "confidence": dict(confidence), "team_score": dict(team_score)}


def load_commute(run: Path, cfg: dict) -> dict:
    data = c.read_json(run / "commute.json", None) or {}
    entries = {}
    for entry in data.get("entries") or []:
        job_id = entry.get("job_id")
        if job_id and entry.get("minutes") is not None:
            entries[job_id] = entry
    commute_cfg = cfg.get("commute") if isinstance(cfg.get("commute"), dict) else {}
    max_minutes = data.get("max_minutes")
    if max_minutes is None:
        max_minutes = commute_cfg.get("max_minutes")
    try:
        max_minutes = float(max_minutes) if max_minutes else 60.0
    except (TypeError, ValueError):
        max_minutes = 60.0
    return {
        "enabled": bool(commute_cfg.get("enabled") or (data.get("approved") and entries)),
        "tool": data.get("tool") or commute_cfg.get("tool") or "",
        "approved": bool(data.get("approved") or commute_cfg.get("enabled")),
        "modes": data.get("modes") or commute_cfg.get("modes") or [],
        "max_minutes": max_minutes,
        "entries": entries,
    }


MODE_CN = {"transit": "地铁/公交", "driving": "驾车", "walking": "步行", "cycling": "骑行"}


def commute_label(entry) -> str:
    if not entry:
        return "—"
    mode = MODE_CN.get(entry.get("mode"), entry.get("mode", ""))
    minutes = entry.get("minutes")
    if minutes is None:
        return "—"
    label = f"{mode} {float(minutes):g} 分钟"
    if entry.get("distance_km") is not None:
        try:
            label += f" / {float(entry['distance_km']):g}km"
        except (TypeError, ValueError):
            pass
    return label


def salary_flags(job, cfg):
    """Return (ok, consider, bad) against the user's expected monthly minimum."""
    se = cfg.get("salary_expect") or {}
    try:
        exp_min = float(se.get("min_k")) if se.get("min_k") else None
    except (TypeError, ValueError):
        exp_min = None
    if not exp_min:
        return True, True, False
    sal = job.get("salary") or {}
    top = sal.get("max_k")
    mid = sal.get("mid_k")
    if top is None and mid is None:
        return False, True, False
    top = float(top if top is not None else mid)
    mid = float(mid if mid is not None else top)
    ok = top >= exp_min * 0.95 or mid >= exp_min * 0.9
    consider = top >= exp_min * 0.85 or mid >= exp_min * 0.8
    return ok, consider, not consider


def commute_flags(job, commute):
    """Return (ok, consider, bad, note)."""
    if not commute.get("enabled"):
        return True, True, False, ""
    entry = commute["entries"].get(job.get("job_id"))
    if not entry:
        return False, False, False, "通勤未计算"
    minutes = float(entry.get("minutes") or 0)
    limit = float(commute.get("max_minutes") or 60)
    if minutes <= limit:
        return True, True, False, ""
    if minutes <= limit * 1.2 + 10:
        return False, True, False, "通勤略超"
    if minutes <= limit * 1.5:
        return False, True, False, "通勤偏远"
    return False, False, True, "超通勤"


def job_recommendation(job, cfg, commute):
    salary_ok, salary_consider, salary_bad = salary_flags(job, cfg)
    commute_ok, commute_consider, commute_bad, commute_note = commute_flags(job, commute)
    if salary_bad:
        return "不推荐", "薪资明显低于期望"
    if commute_bad:
        return "不推荐", "通勤明显超出上限"
    if commute.get("enabled") and job.get("job_id") not in commute["entries"]:
        return "待核实", "通勤未计算"
    if salary_ok and commute_ok:
        return "推荐", ""
    if not salary_ok and not salary_consider:
        return "不推荐", "薪资低于可接受范围"
    return "可考虑", commute_note or ("薪资略低" if not salary_ok else "通勤略远")


def recommendation_summary(jobs, cfg, commute):
    labels = {}
    for job in jobs:
        label, reason = job_recommendation(job, cfg, commute)
        labels[job["job_id"]] = {"label": label, "reason": reason}
    recommended = [jid for jid, v in labels.items() if v["label"] == "推荐"]
    consider = [jid for jid, v in labels.items() if v["label"] == "可考虑"]
    pending = [jid for jid, v in labels.items() if v["label"] == "待核实"]
    not_recommended = [jid for jid, v in labels.items() if v["label"] == "不推荐"]
    if len(recommended) >= 5:
        status = "ok"
    elif recommended or consider or pending:
        status = "partial"
    else:
        status = "insufficient"

    se = cfg.get("salary_expect") or {}
    try:
        exp_min = float(se.get("min_k")) if se.get("min_k") else None
    except (TypeError, ValueError):
        exp_min = None
    tops = [float(j["salary"]["max_k"]) for j in jobs
            if (j.get("salary") or {}).get("max_k") is not None]
    found_top_p50 = percentile(tops, 0.5)
    commute_minutes = [float(e.get("minutes")) for e in commute.get("entries", {}).values()
                       if e.get("minutes") is not None]
    commute_median = percentile(commute_minutes, 0.5)
    commute_max = max(commute_minutes) if commute_minutes else None

    reasons = []
    alternatives = []
    if status == "insufficient":
        if exp_min and found_top_p50 is not None and found_top_p50 < exp_min * 0.85:
            reasons.append(f"期望月薪下限 {exp_min:g}K，抓到的岗位月薪上限中位仅 {found_top_p50:g}K，差距过大")
            alternatives.append(f"把期望薪资下调到 {round(found_top_p50 * 1.1, 1):g}K 左右，或扩大岗位/行业范围")
        if commute.get("enabled") and commute_max is not None and commute_max > commute["max_minutes"] * 1.5:
            reasons.append(f"通勤最长 {commute_max:g} 分钟，明显超过 {commute['max_minutes']:g} 分钟上限")
            alternatives.append(f"把通勤上限放宽到 {int(commute_max)} 分钟，或换区域")
        if commute.get("enabled") and not commute_minutes:
            reasons.append("通勤未计算，无法判断是否符合距离要求")
            alternatives.append("配置地图工具后重算通勤，或先不把通勤作为硬条件")
        if not jobs:
            reasons.append("本次没有抓到岗位")
            alternatives.append("换关键词/城市重试，或放宽岗位与行业范围")
        if not reasons:
            reasons.append("没有岗位同时满足薪资、通勤与基本意向")
        reasons.append("不会把明显不匹配的岗位包装成推荐")
    elif status == "partial":
        if pending:
            reasons.append(f"{len(pending)} 个岗位通勤未计算，结论待核实")
        if consider:
            reasons.append(f"{len(consider)} 个岗位可考虑，但薪资或通勤存在轻微偏差")

    return {
        "status": status,
        "labels": labels,
        "counts": {
            "recommended": len(recommended),
            "consider": len(consider),
            "pending": len(pending),
            "not_recommended": len(not_recommended),
        },
        "recommended_ids": recommended,
        "consider_ids": consider,
        "pending_ids": pending,
        "not_recommended_ids": not_recommended,
        "salary_expected_min": exp_min,
        "salary_found_top_p50": found_top_p50,
        "commute_median": commute_median,
        "commute_max": commute_max,
        "insufficient_reason": "；".join(reasons),
        "alternatives": alternatives,
    }


def commute_summary(jobs, commute):
    if not commute.get("enabled"):
        return {"enabled": False, "tool": "", "max_minutes": None, "calculated": 0,
                "missing": 0, "within_max": 0, "over_max": 0}
    entries = commute["entries"]
    calculated = sum(1 for j in jobs if j.get("job_id") in entries)
    within = sum(1 for j in jobs if j.get("job_id") in entries
                 and float(entries[j["job_id"]].get("minutes") or 0) <= commute["max_minutes"])
    return {
        "enabled": True,
        "tool": commute.get("tool", ""),
        "max_minutes": commute["max_minutes"],
        "calculated": calculated,
        "missing": len(jobs) - calculated,
        "within_max": within,
        "over_max": max(0, calculated - within),
    }


def commute_index(jobs, commute):
    out = {}
    for job in jobs:
        entry = commute["entries"].get(job.get("job_id"))
        if not entry:
            continue
        minutes = float(entry.get("minutes") or 0)
        out[job["job_id"]] = {
            "mode": entry.get("mode", ""),
            "minutes": minutes,
            "distance_km": entry.get("distance_km"),
            "label": commute_label(entry),
            "within_max": minutes <= commute["max_minutes"],
            "over_max": minutes > commute["max_minutes"],
        }
    return out


AGE_ORDER = ["≤3年", "3–5年", "5–10年", "10–20年", "20年+", "未披露"]


def _company_group_stats(companies, key, order=None):
    groups = defaultdict(list)
    for company in companies:
        groups[company.get(key) or "未披露"].append(company)
    out = []
    for label, items in groups.items():
        mids = [m for company in items for m in company.get("mids", [])]
        out.append({
            "label": label,
            "companies": len(items),
            "n": sum(company["jobs"] for company in items),
            "p50": percentile(mids, 0.5),
        })
    if order:
        index = {label: i for i, label in enumerate(order)}
        out.sort(key=lambda x: (index.get(x["label"], 999), -x["companies"]))
    else:
        out.sort(key=lambda x: -x["companies"])
    return out


def company_research(jobs, profiles, company_index):
    grouped = defaultdict(list)
    for job in jobs:
        grouped[job["company_key"]].append(job)

    companies = []
    for key, items in grouped.items():
        entry = company_index.get(key) or {}
        mids = [monthly_mid(j) for j in items if monthly_mid(j) is not None]
        companies.append({
            "company_key": key,
            "display_name": entry.get("display_name") or items[0].get("company", ""),
            "funding": entry.get("funding_stage") or "未披露",
            "industry": entry.get("industry") or "未披露",
            "size": entry.get("size") or "未披露",
            "age": company_age_bucket(entry.get("founded_year")),
            "jobs": len(items),
            "p50": percentile(mids, 0.5),
            "mids": mids,
            "team_score": entry.get("team_score") or {},
        })

    total_jobs = sum(company["jobs"] for company in companies)
    by_funding = _company_group_stats(companies, "funding", FUNDING_ORDER)
    by_industry = _company_group_stats(companies, "industry")
    by_size = _company_group_stats(companies, "size", SIZE_ORDER)
    by_age = _company_group_stats(companies, "age", AGE_ORDER)

    industry_counts = Counter(company["industry"] for company in companies)
    industries = [key for key, _ in industry_counts.most_common() if key != "未披露"][:8]
    stages = [stage for stage in FUNDING_ORDER if any(c["funding"] == stage for c in companies)]
    for stage in sorted({c["funding"] for c in companies}):
        if stage not in stages:
            stages.append(stage)
    cells = []
    max_count = 0
    for i, industry in enumerate(industries):
        for j, stage in enumerate(stages):
            count = sum(1 for c in companies if c["industry"] == industry and c["funding"] == stage)
            if count:
                cells.append([i, j, count])
                max_count = max(max_count, count)

    counts = sorted((company["jobs"] for company in companies), reverse=True)
    total = total_jobs or 1
    top_companies = sorted(companies, key=lambda c: -c["jobs"])[:10]
    concentration = {
        "top5_share_pct": round(sum(counts[:5]) / total * 100, 1),
        "top10_share_pct": round(sum(counts[:10]) / total * 100, 1),
        "single_job_company_pct": round(sum(1 for x in counts if x == 1) / max(1, len(counts)) * 100, 1),
        "hhi": round(sum((x / total) ** 2 for x in counts) * 10000, 1),
    }
    coverage = {
        "founded_pct": round(sum(1 for c in companies if c["age"] != "未披露") / max(1, len(companies)) * 100, 1),
        "industry_pct": round(sum(1 for c in companies if c["industry"] != "未披露") / max(1, len(companies)) * 100, 1),
        "funding_pct": round(sum(1 for c in companies if c["funding"] != "未披露") / max(1, len(companies)) * 100, 1),
    }
    for company in companies:
        company.pop("mids", None)
    return {
        "companies": len(companies),
        "total_jobs": total_jobs,
        "by_funding": by_funding,
        "by_industry": by_industry,
        "by_size": by_size,
        "by_age": by_age,
        "industry_funding": {"industries": industries, "stages": stages, "cells": cells, "max": max_count},
        "concentration": concentration,
        "top_companies": top_companies,
        "coverage": coverage,
    }


def main():
    import argparse

    ap = argparse.ArgumentParser(description="CareeSeek 分析")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    args = ap.parse_args()
    run = c.resolve_run(args.run)

    cfg = c.read_json(run / "config.json", {}) or {}
    normalized = c.read_json(run / "normalized" / "jobs.json", None)
    if not normalized:
        c.die("找不到 normalized/jobs.json，先运行 normalize.py")
    jobs = normalized.get("jobs") or []
    if not jobs:
        c.die("normalized 数据为空，无法分析")
    profiles = load_profiles(run)
    builtin_tiers = load_builtin_tiers()
    commute = load_commute(run, cfg)
    recommendation = recommendation_summary(jobs, cfg, commute)
    commute_sum = commute_summary(jobs, commute)
    commute_idx = commute_index(jobs, commute)

    company_index = {}
    for job in jobs:
        key = job["company_key"]
        profile = profiles.get(key) or {}
        profile_tier = profile.get("tier")
        if profile_tier in ("tier1", "tier2", "tier3"):
            tier, tier_source = profile_tier, "profile"
        else:
            guess = builtin_tier(job.get("company", ""), builtin_tiers)
            tier, tier_source = (guess, "builtin") if guess else ("unknown", "unknown")
        meta = job.get("company_meta") or {}
        entry = company_index.setdefault(key, {
            "company_key": key,
            "display_name": profile.get("display_name") or job["company"],
            "tier": tier,
            "tier_source": tier_source,
            "funding_stage": funding_from(profile, meta),
            "size": profile.get("size") or meta.get("scale") or "",
            "industry": industry_from(profile, meta),
            "founded": profile.get("founded") or (profile.get("extras") or {}).get("成立日期") or "",
            "founded_year": parse_founded_year(profile, meta),
            "team_score": team_background_score(profile),
            "confidence": profile.get("confidence") or "none",
            "risk_signals": profile.get("risk_signals") or [],
            "desensitized": desensitized_label(job) == "是",
            "jobs": 0,
        })
        entry["jobs"] += 1

    company_res = company_research(jobs, profiles, company_index)

    mids = [monthly_mid(j) for j in jobs if monthly_mid(j) is not None]
    overall = dist_stats(mids)
    annual_mids = [
        monthly_mid(j) * ((j.get("salary") or {}).get("months") or 12)
        for j in jobs if monthly_mid(j) is not None
    ]
    annualized = dist_stats(annual_mids)
    widths = [salary_width(j) for j in jobs if salary_width(j) is not None]
    months_counter = Counter((j.get("salary") or {}).get("months") or 12 for j in jobs if monthly_mid(j) is not None)

    def funding_of(job):
        profile = profiles.get(job["company_key"]) or {}
        return funding_from(profile, job.get("company_meta") or {})

    def size_of(job):
        profile = profiles.get(job["company_key"]) or {}
        return (job.get("company_meta") or {}).get("scale") or profile.get("size") or "未披露"

    def industry_of(job):
        profile = profiles.get(job["company_key"]) or {}
        return industry_from(profile, job.get("company_meta") or {})

    salary = {
        "overall": overall,
        "annualized": annualized,
        "histogram": histogram_fixed(mids),
        "annual_histogram": histogram_annual(annual_mids),
        "templates": salary_templates(jobs),
        "months": [{"months": m, "count": n} for m, n in sorted(months_counter.items())],
        "width": dist_stats(widths),
        "by_experience": group_stats(jobs, exp_bucket, EXP_ORDER),
        "by_scope": group_stats(jobs, scope_bucket),
        "by_funding": group_stats(jobs, funding_of, FUNDING_ORDER),
        "by_size": group_stats(jobs, size_of, SIZE_ORDER),
        "by_industry": group_stats(jobs, industry_of),
        "by_district": group_stats(jobs, lambda j: j.get("district") or "未标注"),
        "by_education": group_stats(jobs, lambda j: j.get("education") or "不限"),
        "by_desensitized": group_stats(jobs, desensitized_label, ["否", "是"]),
    }

    ladders = {
        "same_company": same_company_ladder(jobs, profiles),
        "cross_company": cross_company_matrix(jobs, profiles),
        "capability_map": capability_map(jobs, overall["p50"]),
        "salary_curve": salary_curve(jobs),
    }

    scores = []
    for job in jobs:
        scores.append({"job_id": job["job_id"], "score": match_score(job, cfg, profiles.get(job["company_key"]))})
    score_map = {x["job_id"]: x["score"] for x in scores}
    ranked = sorted([
        {"job_id": j["job_id"], "title": j["title"], "company": j["company"], "city": j.get("city", ""),
         "mid_k": monthly_mid(j), "score": score_map[j["job_id"]],
         "commute": commute_idx.get(j["job_id"], {}),
         "recommendation": recommendation["labels"].get(j["job_id"], {})}
        for j in jobs
    ], key=lambda x: -x["score"])[:20]

    anomalies = []
    for job in jobs:
        sal = job.get("salary") or {}
        mid = monthly_mid(job)
        if sal.get("min_k") is not None and sal.get("max_k") is not None and sal["min_k"] > sal["max_k"]:
            anomalies.append({"type": "salary_inverted", "job_id": job["job_id"], "detail": sal.get("text", "")})
        if mid is not None and (mid < 3 or mid > 150):
            anomalies.append({"type": "salary_extreme", "job_id": job["job_id"], "detail": mid})
    dup_groups = defaultdict(list)
    for job in jobs:
        dup_groups[job.get("dup_hash") or job["job_id"]].append(job["job_id"])
    duplicates = [ids for ids in dup_groups.values() if len(ids) > 1]
    if duplicates:
        anomalies.append({"type": "duplicate_posts", "count": len(duplicates),
                          "examples": [ids[:3] for ids in duplicates[:5]]})

    data_quality = dict(normalized.get("quality") or {})
    data_quality.update({
        "job_count": len(jobs),
        "salary_valid": overall["n"],
        "width_median": percentile(widths, 0.5),
        "months_over12_pct": round(sum(1 for m, n in months_counter.items() if m > 12 for _ in range(n)) / overall["n"] * 100, 1) if overall["n"] else 0,
        "commute_enabled": bool(commute["enabled"]),
        "commute_calculated": commute_sum["calculated"],
        "commute_missing": commute_sum["missing"],
        "commute_coverage_pct": round(commute_sum["calculated"] / len(jobs) * 100, 1) if commute["enabled"] and jobs else None,
    })

    companies = []
    grouped = defaultdict(list)
    for job in jobs:
        grouped[job["company_key"]].append(job)
    for key, items in grouped.items():
        vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
        st = dist_stats(vals)
        entries = company_index.get(key) or {}
        companies.append({"company_key": key, "display_name": entries.get("display_name") or items[0]["company"],
                          "n": len(items), "p50": st["p50"], "p75": st["p75"],
                          "tier": entries.get("tier", "unknown"), "desensitized": desensitized_label(items[0]) == "是"})
    companies.sort(key=lambda x: -x["n"])

    low_confidence_flags = []
    if overall["n"] < 20:
        low_confidence_flags.append(f"有效薪资样本仅 {overall['n']} 条，结论置信度低")
    if data_quality.get("missing_salary_pct", 0) > 30:
        low_confidence_flags.append(f"{data_quality['missing_salary_pct']}% 岗位缺失薪资")
    if data_quality.get("detail_coverage_pct", 0) < 50:
        low_confidence_flags.append("JD 详情覆盖率不足 50%，技能分析可能偏差")
    if data_quality.get("width_median") and data_quality["width_median"] > 8:
        low_confidence_flags.append(
            f"薪资区间宽度中位 {data_quality['width_median']}K，用中值单点代表岗位约有 ±{data_quality['width_median'] / 2:.1f}K 误差")
    founders = founder_stats(profiles, company_index)
    if founders["companies"] and founders["with_founder"] / founders["companies"] < 0.6:
        low_confidence_flags.append(
            f"仅 {founders['with_founder']}/{founders['companies']} 家公司查到创始人姓名，背调覆盖不完整")
    if commute["enabled"] and commute_sum["missing"]:
        low_confidence_flags.append(
            f"{commute_sum['missing']} 个岗位通勤未计算，推荐结论降为「待核实」")
    if not commute["enabled"] and (cfg.get("commute") or {}).get("enabled"):
        low_confidence_flags.append("用户要求通勤匹配，但还没有地图计算结果（commute.json）")

    analysis = {
        "run_id": run.name,
        "generated_at": c.now_iso(),
        "n": len(jobs),
        "salary": salary,
        "skills": skill_stats(jobs, overall["p50"]),
        "titles": title_stats(jobs),
        "keyword_cloud": keyword_cloud(jobs),
        "jd": jd_stats(jobs),
        "founders": founders,
        "company_research": company_res,
        "companies": companies[:12],
        "ladders": ladders,
        "scores": scores,
        "ranked_jobs": ranked,
        "company_index": sorted(company_index.values(), key=lambda x: -x["jobs"]),
        "anomalies": anomalies,
        "data_quality": data_quality,
        "commute": {**commute_sum, "approved": commute["approved"], "modes": commute["modes"]},
        "commute_index": commute_idx,
        "recommendation": recommendation,
        "low_confidence_flags": low_confidence_flags,
    }
    c.write_json(run / "analysis.json", analysis)

    state = c.load_state(run)
    state["stage"] = "analyzed"
    c.save_state(run, state)

    c.emit({
        "run": str(run),
        "n": len(jobs),
        "salary_monthly": overall,
        "salary_annualized": annualized,
        "width_median": data_quality.get("width_median"),
        "top_companies": [x["display_name"] for x in companies[:5]],
        "skills_top": [x["skill"] for x in analysis["skills"]["top"][:8]],
        "keyword_cloud_top": [x["text"] for x in analysis["keyword_cloud"][:10]],
        "founders": founders,
        "company_research": {
            "companies": company_res["companies"],
            "funding_top": company_res["by_funding"][:3],
            "industry_top": company_res["by_industry"][:3],
            "concentration": company_res["concentration"],
            "team_score": founders.get("team_score", {}),
        },
        "commute": commute_sum,
        "recommendation": {
            "status": recommendation["status"],
            "counts": recommendation["counts"],
            "reason": recommendation["insufficient_reason"],
            "alternatives": recommendation["alternatives"],
        },
        "low_confidence_flags": low_confidence_flags,
        "output": str(run / "analysis.json"),
        "next": "运行 report.py 生成 HTML 报告",
    })


if __name__ == "__main__":
    main()
