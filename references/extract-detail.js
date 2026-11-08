// 在 Boss直聘「岗位详情页」的页面上下文中执行。
// 返回 { source_url, card: {...}, detail: {...} }，可直接交给
//   python scripts/ingest.py --run <run> --kind jobs --file - --extraction-mode detail
(() => {
  const pick = (selectors) => {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
    }
    return "";
  };

  const benefits = Array.from(document.querySelectorAll(
    ".job-tags span, .job-benefits .tag-all span, .job-benefits .tag-all .tag-item"
  )).map((x) => (x.innerText || "").trim()).filter(Boolean);

  return {
    source_url: location.href,
    card: {
      title: pick([".job-banner .name h1", ".job-banner .name", ".job-name"]),
      company: pick([".sider-company .company-info", ".job-banner .company-info h3", ".company-info .company-name"]),
      salary_text: pick([".job-banner .salary", ".salary"]),
      city: pick([".job-banner .text-city", ".job-banner .info .text-city"]),
      exp_text: pick([".job-banner .text-experiece", ".job-banner .info .text-experiece"]),
      edu: pick([".job-banner .text-degree", ".job-banner .info .text-degree"]),
      tags: []
    },
    detail: {
      raw_text: pick([".job-sec-text", ".job-detail-section .job-sec-text", ".job-detail"]),
      posted_at: pick([".job-banner .info .time", ".job-time"]),
      benefits
    }
  };
})()
