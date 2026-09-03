/* AF e2e: канон-бейдж демо-режима + удаление чипа 🎭 из футера. */
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
    await page.waitForSelector(".admin-shell__sidebar-demo", { visible: true, timeout: 15000 });

    const demoState = await page.evaluate(() => {
      const badge = document.querySelector(".admin-shell__sidebar-demo");
      const cs = getComputedStyle(badge);
      const brand = document.querySelector(".admin-shell__brand");
      const nav = document.querySelector(".admin-shell__nav--main");
      const orderOk =
        brand.compareDocumentPosition(badge) & Node.DOCUMENT_POSITION_FOLLOWING &&
        badge.compareDocumentPosition(nav) & Node.DOCUMENT_POSITION_FOLLOWING;
      return {
        text: badge.textContent.trim(),
        bg: cs.backgroundColor,
        color: cs.color,
        orderOk,
        chipInFooter: !!document.querySelector(".admin-shell__sidebar-session .ai-status--emoji"),
      };
    });
    check("бейдж виден в демо-сессии", true);
    check("текст канон: «🔒 Демо-режим: только просмотр»", demoState.text === "🔒 Демо-режим: только просмотр", demoState.text);
    check("под брендом, над меню", demoState.orderOk);
    check("янтарный тинт + токен --warning", /245,\s*158,\s*11/.test(demoState.bg) && (/(210,\s*153,\s*34)|(180,\s*83,\s*9)/.test(demoState.color)), `${demoState.bg} / ${demoState.color}`);
    check("чип 🎭 из футера удалён", !demoState.chipInFooter);

    // Светлая тема: фон тинта переключается
    await page.click(".admin-shell__sidebar-btn");
    await new Promise((r) => setTimeout(r, 300));
    const lightBg = await page.evaluate(() => getComputedStyle(document.querySelector(".admin-shell__sidebar-demo")).backgroundColor);
    check("светлая тема: тинт переключается", /180,\s*83,\s*9/.test(lightBg), lightBg);
    await page.click(".admin-shell__sidebar-btn");
    await new Promise((r) => setTimeout(r, 300));

    // Выход → логинформа; бейдж ушёл вместе с сессией
    await page.click(".admin-shell__sidebar-logout");
    await new Promise((r) => setTimeout(r, 500));
    const afterLogout = await page.evaluate(() => ({
      login: location.pathname.includes("login") || !!document.querySelector(".login-form"),
      badgeGone: !document.querySelector(".admin-shell__sidebar-demo"),
    }));
    check("«Выйти» → логинформа, бейдж исчез", afterLogout.login && afterLogout.badgeGone);

    // Админ-сессия: бейдж не рендерится (условный рендер по role === demo)
    await page.goto(BASE + "/login", { waitUntil: "networkidle0" });
    await page.type("input[type='password']", process.env.AF_ADMIN_TOKEN);
    await page.click(".login-form button[type='submit']");
    await page.waitForSelector(".admin-shell__sidebar-btn", { timeout: 15000 });
    await new Promise((r) => setTimeout(r, 600));
    const adminState = await page.evaluate(() => ({
      badgeGone: !document.querySelector(".admin-shell__sidebar-demo"),
      chipInFooter: !!document.querySelector(".admin-shell__sidebar-session .ai-status--emoji"),
    }));
    check("админ-сессия: бейдж не рендерится", adminState.badgeGone);
    check("админ-сессия: чип роли в футере отсутствует", !adminState.chipInFooter);

    check("0 JS-ошибок", jsErrors.length === 0, jsErrors.join("; ").slice(0, 200));
  } finally {
    await browser.close();
  }
  const fails = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - fails}/${results.length} PASS`);
  process.exit(fails ? 1 : 0);
})();