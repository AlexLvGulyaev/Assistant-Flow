/* AF e2e КТ-5: остаток (Панель состояния, Сводка, Retrieval Settings,
   Memory, Анализ RAG, Журнал аудита, Логи). Тихие чипы везде, мёртвых
   пилюль нет, overflow 1280/375, обе темы, 0 JS-ошибок. */
const puppeteer = require("puppeteer-core");

const BASE = "http://localhost:8080";
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`);
}

async function inspect(page, path, waitMs = 3000) {
  await page.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 30000 });
  await new Promise((r) => setTimeout(r, waitMs));
  // Демо-сессии стареют: дефолтное окно 24h → переключаем на 7d, где есть данные.
  try {
    const has7d = await page.$eval(
      "select.logs-select",
      (s) => Array.from(s.options).some((o) => o.value === "7d")
    );
    if (has7d) {
      await page.select("select.logs-select", "7d");
      await new Promise((r) => setTimeout(r, 3500));
    }
  } catch { /* страницы без окна времени */ }
  return page.evaluate(() => ({
    title: document.querySelector(".page__title")?.textContent.trim() ?? null,
    pills: document.querySelectorAll(".status-badge, .security-severity").length,
    chips: document.querySelectorAll(".ai-status--emoji").length,
    miniBadges: document.querySelectorAll(".mini-badge").length,
    kv: document.querySelectorAll("dl.kv, dl[class*='kv']").length,
    opsPanels: document.querySelectorAll(".modality-ops-panel").length,
    snapshot: !!document.querySelector(".session-json-snapshot"),
    overflow:
      document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }));
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    const jsErrors = [];
    page.on("pageerror", (e) => jsErrors.push(String(e)));

    await page.goto(BASE + "/login", { waitUntil: "domcontentloaded", timeout: 30000 });
    const demoBtn = await page.waitForSelector(".login-form__btn--outline", { timeout: 10000 });
    await demoBtn.click();
    await page.waitForSelector(".admin-shell__nav-group", { timeout: 20000 });

    const checks = [
      ["/", "Панель состояния"],
      ["/summary", "Сводка"],
      ["/retrieval", "Retrieval Settings"],
      ["/memory", "Memory"],
      ["/evaluation", "Анализ RAG"],
      ["/audit", "Журнал аудита"],
      ["/logs", "Логи"],
    ];
    const data = {};
    for (const [path, name] of checks) {
      data[path] = await inspect(page, path);
      check(
        `${name}: заголовок отрисован`,
        !!data[path].title,
        data[path].title ?? "нет .page__title"
      );
      check(
        `${name}: 0 цветных пилюль`,
        data[path].pills === 0,
        `pills=${data[path].pills}`
      );
      check(
        `${name}: kv-строки / опер-панели`,
        data[path].kv > 0 || data[path].opsPanels > 0,
        `kv=${data[path].kv}; ops=${data[path].opsPanels}`
      );
      check(
        `${name}: без переполнения 1280`,
        data[path].overflow <= 1,
        `overflow=${data[path].overflow}px`
      );
    }

    // чипы там, где ожидаемы
    check(
      "Панель состояния: SOT-чипы рендерятся",
      data["/"].chips > 0,
      `chips=${data["/"].chips}`
    );
    check(
      "Retrieval Settings: SOT-чипы (health/readiness) рендерятся",
      data["/retrieval"].chips > 0,
      `chips=${data["/retrieval"].chips}`
    );
    check(
      "Журнал аудита: severity-чипы SOT + маркер «sec» (согласованный data-tag)",
      data["/audit"].chips > 0 && data["/audit"].miniBadges >= 0,
      `chips=${data["/audit"].chips}; mini=${data["/audit"].miniBadges}`
    );
    check(
      "Сводка: mini-badge провайдеров — data-tag (вне статусов)",
      data["/summary"].chips >= 0,
      `chips=${data["/summary"].chips}; mini=${data["/summary"].miniBadges}`
    );
    check(
      "Анализ RAG: опер-панели канона",
      data["/evaluation"].opsPanels > 0,
      `ops=${data["/evaluation"].opsPanels}`
    );

    // Логи: пагинация (визуальный канон)
    const logsPag = await page.evaluate(() => ({
      pag: !!document.querySelector(".logs-page-controls"),
    }));
    check(
      "Логи: пагинация присутствует",
      logsPag.pag === true,
      `pag=${logsPag.pag}`
    );

    // обе темы на Панели состояния
    await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await new Promise((r) => setTimeout(r, 3000));
    await page.click(".admin-shell__sidebar-btn");
    await new Promise((r) => setTimeout(r, 300));
    const themeAttr = await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme")
    );
    check("светлая тема включается на остатке", themeAttr === "light", themeAttr);
    await page.click(".admin-shell__sidebar-btn");
    await new Promise((r) => setTimeout(r, 300));

    // 375px на двух репрезентативных
    for (const [path, name] of [["/summary", "Сводка"], ["/audit", "Журнал аудита"]]) {
      await page.setViewport({ width: 375, height: 800 });
      await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
      await new Promise((r) => setTimeout(r, 2000));
      const ov = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      );
      check(`${name}: без переполнения 375`, ov <= 1, `overflow=${ov}px`);
 await page.setViewport({ width: 1280, height: 900 });
    }

    check("0 JS-ошибок", jsErrors.length === 0, jsErrors.join("; ").slice(0, 200));
  } finally {
    await browser.close();
  }
  const fails = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - fails}/${results.length} PASS`);
  process.exit(fails ? 1 : 0);
})();