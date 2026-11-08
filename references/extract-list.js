// 在 Boss直聘「搜索列表页」的页面上下文中执行（execute_js / javascript 工具）。
// 返回 { page, total, items: [{ source_url, card: {...} }] }。
// 若结构变化导致返回空数组，按 playbook-boss.md 的修复协议更新 selectors.json，而不是改脚本。
(() => {
  const pick = (root, selectors) => {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
    }
    return "";
  };

  const cardSelectors = [".job-card-wrapper", "li.job-card-box", ".job-list-box .job-card-wrapper"];
  let cards = [];
  for (const sel of cardSelectors) {
    const found = Array.from(document.querySelectorAll(sel));
    if (found.length > cards.length) cards = found;
  }

  const items = cards.map((c) => {
    const link = c.querySelector("a.job-card-left, a[href*='/job_detail/']");
    let href = link ? link.getAttribute("href") || "" : "";
    if (href && !/^https?:/i.test(href)) href = location.origin + href;

    const tags = Array.from(c.querySelectorAll(".job-tags span, .tag-list li"))
      .map((x) => (x.innerText || "").trim())
      .filter(Boolean);

    return {
      source_url: href,
      card: {
        title: pick(c, [".job-name", ".job-title"]),
        company: pick(c, [".company-name", ".company-info h3"]),
        salary_text: pick(c, [".salary", ".job-salary"]),
        city: pick(c, [".job-area", ".job-area-wrapper"]),
        exp_text: tags.find((t) => /年|经验|应届|不限/.test(t)) || "",
        edu: tags.find((t) => /本科|硕士|大专|博士|学历/.test(t)) || "",
        tags
      }
    };
  }).filter((x) => x.card.title && x.card.company);

  return { page: location.href, total: items.length, items };
})()
