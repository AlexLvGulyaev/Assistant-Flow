/* AF e2e: превью ассетов только авторизованным fetch — нигде не остаётся
   <img>/<a> с прямым src=/api/assets/preview (тот рождает нативный
   пароль-диалог по 401 Basic). Прямые запросы без Authorization = FAIL. */
const puppeteer = require("puppeteer-core");
const BASE = "http://localhost:8080";
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " : ""}${detail ?? ""}`);
}
(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    const unauthAssets = [];
    page.on("request", (req) => {
      const u = req.url();
      if (u.includes("/api/assets/") && !req.headers()["authorization"]) {
        unauthAssets.push(u.slice(0, 90));
      }
    });
    const jsErrors = [];
    page.on("pageerror", (e) => jsErrors.push(String(e)));

    await page.goto(BASE + "/login", { waitUntil: "domcontentloaded" });
    await (await page.waitForSelector(".login-form__btn--outline", { timeout: 10000 })).click();
    await page.waitForSelector(".admin-shell__nav-group", { timeout: 20000 });

    for (const [path, name] of [["/text", "Текст"], ["/images", "Изображения"], ["/audio", "Аудио"]]) {
      await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
      await new Promise((r) => setTimeout(r, 3000));
      const st = await page.evaluate(() => ({
        rawImgs: Array.from(document.querySelectorAll("img")).filter((i) =>
          (i.getAttribute("src") ?? "").includes("/api/assets/")
        ).length,
      }));
      check(`${name}: 0 <img> с прямым src=/api/assets`, st.rawImgs === 0, `raw=${st.rawImgs}`);
    }
    check(
      "запросы /api/assets/* без Authorization отсутствуют",
      unauthAssets.length === 0,
      unauthAssets.join("; ") || "нет"
    );
    check("0 JS-ошибок", jsErrors.length === 0, jsErrors.join("; ").slice(0, 150));
  } finally {
    await browser.close();
  }
  const fails = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - fails}/${results.length} PASS`);
  process.exit(fails ? 1 : 0);
})();
