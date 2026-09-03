/* AF e2e КТ-3: меню-канон + эмодзи-SOT чипы + «Обозначения». */
const puppeteer = require("puppeteer-core");

const BASE = "http://localhost:8080";
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`);
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

    await page.goto(BASE + "/login", { waitUntil: "networkidle0", timeout: 30000 });
    const demoBtn = await page.waitForSelector(".login-form__btn--outline", { timeout: 10000 });
    await demoBtn.click();
    await page.waitForSelector(".admin-shell__nav-group", { timeout: 15000 });

    // 1. Меню-канон: группы, порядок, эмодзи, ренеймы
    const menu = await page.evaluate(() =>
      Array.from(document.querySelectorAll(".admin-shell__nav-group")).map((g) => ({
        title: g.querySelector(".admin-shell__nav-group-title")?.textContent.trim(),
        items: Array.from(g.querySelectorAll(".admin-shell__nav-link .admin-shell__nav-label")).map(
          (l) => l.textContent.trim()
        ),
        icons: Array.from(g.querySelectorAll(".admin-shell__nav-icon")).map((i) => i.textContent.trim()),
        rawDiamond: Array.from(g.querySelectorAll(".admin-shell__nav-icon")).some((i) =>
          i.textContent.includes("◇")
        ),
      }))
    );
    check(
      "группы и порядок (канон)",
      JSON.stringify(menu.map((g) => g.title)) ===
        JSON.stringify(["Система", "База знаний", "Модальности", "Аналитика", "Наблюдаемость", "Справка"]),
      menu.map((g) => g.title).join(" › ")
    );
    const byTitle = Object.fromEntries(menu.map((g) => [g.title, g]));
    check(
      "Система: Панель состояния + Retrieval Settings",
      byTitle["Система"].items.join(",") === "Панель состояния,Retrieval Settings",
      byTitle["Система"].items.join(",")
    );
    check("База знаний: Документы", byTitle["База знаний"].items.join(",") === "Документы");
    check(
      "Модальности: Текст, RAG, Изображения, Аудио",
      byTitle["Модальности"].items.join(",") === "Текст,RAG,Изображения,Аудио",
      byTitle["Модальности"].items.join(",")
    );
    check("Аналитика: Сводка, Анализ RAG", byTitle["Аналитика"].items.join(",") === "Сводка,Анализ RAG");
    check(
      "Наблюдаемость: Логи, Memory, Журнал аудита",
      byTitle["Наблюдаемость"].items.join(",") === "Логи,Memory,Журнал аудита",
      byTitle["Наблюдаемость"].items.join(",")
    );
    check("Справка: Обозначения", byTitle["Справка"].items.join(",") === "Обозначения");
    check("иконки-эмодзи вместо ◇", menu.every((g) => !g.rawDiamond) && byTitle["Справка"].icons[0] === "🗺️");

    // 2. «Обозначения»: страница, канон RF (сетка/панели/хэлп/строки)
    const legendLink = await page.evaluateHandle(() =>
      Array.from(document.querySelectorAll('a[href="/legend"]')).find((a) => a.textContent.includes("Обозначения"))
    );
    await legendLink.asElement().click();
    await page.waitForSelector(".legend-grid", { timeout: 10000 });
    const legend = await page.evaluate(() => ({
      title: document.querySelector(".page__title")?.textContent.trim(),
      intro: !!document.querySelector(".legend-intro"),
      panels: document.querySelectorAll(".legend-panel").length,
      rows: document.querySelectorAll(".legend-row").length,
      helps: document.querySelectorAll(".legend-help__btn").length,
      iconLg: !!document.querySelector(".legend-row .ai-status--icon-lg"),
      firstLabels: Array.from(document.querySelectorAll(".legend-row__label")).slice(0, 4).map((l) => l.textContent.trim()),
    }));
    check("страница «Обозначения» открылась", legend.title === "Обозначения", legend.title);
    check("канон-разметка: интро, 6 панелей, 6 хэлпов, icon-lg", legend.intro && legend.panels === 6 && legend.helps === 6 && legend.iconLg, JSON.stringify(legend));
    check("полный SOT: 6 семей, ~38 строк, лейблы из chipContract", legend.rows >= 36 && legend.rows <= 40, `rows=${legend.rows}; ${legend.firstLabels.join(" | ")}`);

    // хэлп-поповер
    await page.hover(".legend-help__btn");
    await new Promise((r) => setTimeout(r, 400));
    const popVisible = await page.evaluate(() => {
      const pop = document.querySelector(".legend-help__pop");
      return pop ? getComputedStyle(pop).visibility === "visible" : false;
    });
    check("«?»-хэлп-поповер показывается", popVisible);

    // 3. Регресс темы на легенде
    await page.click(".admin-shell__sidebar-btn");
    await new Promise((r) => setTimeout(r, 300));
    const panelBgLight = await page.evaluate(
      () => getComputedStyle(document.querySelector(".legend-panel")).backgroundColor
    );
    check("легенда в светлой теме: панель серо-голубая", /231,\s*235,\s*243/.test(panelBgLight), panelBgLight);
    await page.click(".admin-shell__sidebar-btn");
    await new Promise((r) => setTimeout(r, 300));

    // 4. Статус-чипы (SOT) на «Панели состояния»: тихие ai-status вместо status-badge
    const dashLink = await page.evaluateHandle(() =>
      Array.from(document.querySelectorAll('a[href="/"]')).find((a) => a.textContent.includes("Панель состояния"))
    );
    await dashLink.asElement().click();
    await new Promise((r) => setTimeout(r, 3000));
    const chips = await page.evaluate(() => ({
      title: document.querySelector(".page__title")?.textContent.trim(),
      badges: document.querySelectorAll(".status-badge").length,
      chips: document.querySelectorAll(".ai-status--emoji").length,
      sample: Array.from(document.querySelectorAll(".ai-status--emoji")).slice(0, 6).map((c) => c.textContent.trim()),
      bgSample: (() => {
        const el = document.querySelector(".ai-status--emoji");
        return el ? getComputedStyle(el).backgroundColor : null;
      })(),
    }));
    check("страница «Панель состояния»", chips.title === "Панель состояния", chips.title);
    check("цветных .status-badge больше нет", chips.badges === 0, `badges=${chips.badges}`);
    check("тихие эмодзи-чипы рендерятся", chips.chips > 0, `chips=${chips.chips}; sample=${chips.sample.join(" | ")}`);
    check("чип прозрачный (quiet)", chips.bgSample === "rgba(0, 0, 0, 0)", chips.bgSample);

    // 5. «Журнал аудита»: серьёзность — эмодзи-чипы
    const auditLink = await page.evaluateHandle(() =>
      Array.from(document.querySelectorAll('a[href="/audit"]')).find((a) => a.textContent.includes("Журнал аудита"))
    );
    await auditLink.asElement().click();
    await new Promise((r) => setTimeout(r, 3000));
    const audit = await page.evaluate(() => ({
      title: document.querySelector(".page__title")?.textContent.trim(),
      severityChips: document.querySelectorAll(".ai-status--emoji").length,
      severityBadges: document.querySelectorAll(".security-severity").length,
    }));
    check("страница «Журнал аудита» (ренейм)", audit.title === "Журнал аудита", audit.title);
    check("severity-чипы эмодзи вместо security-severity", audit.severityChips > 0 && audit.severityBadges === 0, JSON.stringify(audit));

    // 6. Переполнение 375/1280 на легенде
    for (const width of [1280, 375]) {
      await page.setViewport({ width, height: 900 });
      await page.goto(BASE + "/legend", { waitUntil: "networkidle0", timeout: 30000 });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      );
      check(`легенда ${width}px: без горизонтального переполнения`, overflow <= 1, `overflow=${overflow}px`);
    }

    check("0 JS-ошибок", jsErrors.length === 0, jsErrors.join("; ").slice(0, 200));
  } finally {
    await browser.close();
  }
  const fails = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - fails}/${results.length} PASS`);
  process.exit(fails ? 1 : 0);
})();