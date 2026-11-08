// 列表页「接口抽取」优先方案：在页面上下文中用同源 fetch 读取搜索接口。
// 优点：薪资为明文（DOM 中的薪资数字是自定义字体渲染的）、自带公司行业/规模/融资阶段。
// 用法：先设置参数，再执行本脚本：
//   page.evaluate(() => { window.__CAREE_PARAMS__ = { query: "AI产品经理", city: "101020100", page: 1, pageSize: 15 }; });
//   page.evaluate(<本文件内容>)
// 返回 { code, message, resCount, hasMore, total, items: [...] }。
(async () => {
  const p = window.__CAREE_PARAMS__ || {};
  const query = p.query || "AI产品经理";
  const city = p.city || "100010000";
  const page = p.page || 1;
  const pageSize = p.pageSize || 15;

  const url =
    "/wapi/zpgeek/search/joblist.json?scene=1&query=" +
    encodeURIComponent(query) +
    "&city=" + encodeURIComponent(city) +
    "&page=" + page +
    "&pageSize=" + pageSize;

  let res, data;
  try {
    res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) return { error: "http_" + res.status, status: res.status, items: [], total: 0 };
    data = await res.json();
  } catch (e) {
    return { error: String(e && e.message || e), items: [], total: 0 };
  }

  const zp = data.zpData || {};
  const list = zp.jobList || [];
  const items = list.map((j) => {
    const cityText = [j.cityName, j.areaDistrict, j.businessDistrict].filter(Boolean).join("·");
    return {
      source_url: "https://www.zhipin.com/job_detail/" + (j.encryptJobId || "") + ".html",
      job_id: j.encryptJobId || "",
      search_keyword: query,
      page: page,
      card: {
        title: j.jobName || "",
        company: j.brandName || "",
        salary_text: j.salaryDesc || "",
        city: cityText,
        exp_text: j.jobExperience || "",
        edu: j.jobDegree || "",
        tags: [].concat(j.skills || [], (j.welfareList || []).slice(0, 5))
      },
      meta: {
        brand_stage: j.brandStageName || "",
        brand_industry: j.brandIndustry || "",
        brand_scale: j.brandScaleName || "",
        security_id: j.securityId || "",
        encrypt_boss_id: j.encryptBossId || ""
      }
    };
  }).filter((x) => x.card.title && x.card.company);

  return {
    code: data.code,
    message: data.message,
    resCount: zp.resCount || 0,
    hasMore: !!zp.hasMore,
    total: items.length,
    items: items
  };
})()
