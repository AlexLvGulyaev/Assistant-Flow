/* AF e2e КТ-4 (pairwise ядро): Текст/RAG/Изображения/Аудио/Документы.
   Проверяет pairwise-канон: тихие чипы в головах деталей, панели
   («Параметры сессии» первой), «Технические данные» (SessionJsonSnapshot). */
const puppeteer = require("puppeteer-core");

const BASE = "http://localhost:8080";
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`);
}

async function inspect(page, path) {
  await page.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  // Демо-сессии стареют: окно UI по умолчанию 24h — переключаем на 7d,
  // чтобы проверки не зависели от «свежести» данных.
  try {
    await page.select('[aria-label="Окно времени"]', "7d");
    await new Promise((r) => setTimeout(r, 3500));
  } catch { /* страницы без окна времени — оставляем дефолт */ }
  return page.evaluate(() => {
    const head = document.querySelector(".modality-card__head");
    const titles = Array.from(document.querySelectorAll(".modality-ops-panel__name")).map((n) =>
      n.textContent.trim()
    );
    return {
      pills: document.querySelectorAll(".status-badge").length,
      headChip: head ? !!head.querySelector(".ai-status--emoji") : null,
      headChipText: head?.querySelector(".ai-status--emoji")?.textContent.trim() ?? null,
      panels: titles.slice(0, 6),
      snapshot: !!document.querySelector(".session-json-snapshot"),
      snapshotText: Array.from(document.querySelectorAll(".session-json-snapshot__head, .session-json-snapshot__summary, details.session-json-snapshot > summary"))
        .slice(0, 3)
        .map((e) => e.textContent.trim()),
      kvRows: document.querySelectorAll(".kv.modality-ops-panel__kv").length,
      gaps: document.querySelectorAll(".telemetry-gap").length,
      overflow:
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
    };
  });
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

    const pages = [
      ["text", "Текст"],
      ["rag", "RAG"],
      ["images", "Изображения"],
      ["audio", "Аудио"],
    ];
    const data = {};
    for (const [path, name] of pages) {
      data[path] = await inspect(page, "/" + path);
      check(
        `${name}: цветных пилюль нет, тихий чип в голове детали`,
        data[path].pills === 0 && data[path].headChip === true,
        `pills=${data[path].pills}; chip=${data[path].headChipText}`
      );
      check(
        `${name}: панель «Параметры сессии» первая (pairwise)`,
        (data[path].panels[0] ?? "").startsWith("Параметры сессии"),
        data[path].panels.join(" | ")
      );
      check(
        `${name}: «Технические данные» (SessionJsonSnapshot) на странице`,
        data[path].snapshot === true,
        `snapshot=${data[path].snapshot}`
      );
      check(
        `${name}: kv-строки + TelemetryGap в опер-панелях`,
        data[path].kvRows > 0 && data[path].gaps > 0,
        `kv=${data[path].kvRows}; gaps=${data[path].gaps}`
      );
      check(
        `${name}: без горизонтального переполнения (1280)`,
        data[path].overflow <= 1,
        `overflow=${data[path].overflow}px`
      );
    }

    // pairwise: слот 1 = «Параметры сессии» у всех, слот 2 = pipeline-панель
    // модальности (имя своё, позиция общая)
    check(
      "pairwise: слот 2 = pipeline-панель модальности у Текст/Изображения/Аудио",
      /пайплайн|pipeline/i.test(data.text.panels[1] ?? "") &&
        /пайплайн|pipeline/i.test(data.images.panels[1] ?? "") &&
        /пайплайн|pipeline/i.test(data.audio.panels[1] ?? ""),
      `${data.text.panels[1]} / ${data.images.panels[1]} / ${data.audio.panels[1]}`
    );
    check(
      "pairwise: у RAG «Параметры сессии» + RAG-специфика (Качество/Retrieval)",
      data.rag.panels.includes("Качество") && data.rag.panels.includes("Retrieval"),
      data.rag.panels.join(" | ")
    );

    // Документы: выбор документа → timeline с «Техническими данными»
    await page.goto(BASE + "/documents", { waitUntil: "domcontentloaded", timeout: 30000 });
    await new Promise((r) => setTimeout(r, 3000));
    const firstItem = await page.$(".logs-item");
    if (firstItem) {
      await firstItem.click();
      await new Promise((r) => setTimeout(r, 2000));
    }
    const docs = await page.evaluate(() => ({
      pills: document.querySelectorAll(".status-badge").length,
      snapshot: !!document.querySelector(".session-json-snapshot"),
      docsEmpty: !!document.querySelector(".docs-detail-placeholder") &&
        document.querySelectorAll(".logs-item").length === 0,
      overflow:
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
    }));
    check(
      "Документы: 0 пилюль; snapshot виден (демо: список пуст — placeholder)",
      docs.pills === 0 && (docs.snapshot === true || docs.docsEmpty === true),
      `snapshot=${docs.snapshot}; pills=${docs.pills}; docsEmpty=${docs.docsEmpty}; overflow=${docs.overflow}px`
    );

    check("0 JS-ошибок на ядре", jsErrors.length === 0, jsErrors.join("; ").slice(0, 200));
  } finally {
    await browser.close();
  }
  const fails = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - fails}/${results.length} PASS`);
  process.exit(fails ? 1 : 0);
})();