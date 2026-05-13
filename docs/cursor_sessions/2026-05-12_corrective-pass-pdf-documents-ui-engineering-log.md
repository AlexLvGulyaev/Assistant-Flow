# Engineering log: корректирующий проход — PDF cleanup и Documents UI (2026-05-12)

## Корневая причина слабой очистки PDF

После Phase 2 основной шум (`Страница N из M`, колонтитулы) почти не трогался: в **`PdfExtractor`** оставалась только узкая эвристика и нормализация пробелов; общий **`clean_extracted_text`** удаляет в основном пустые строки и ограниченный набор «мусорных» строк на английском, **не покрывая** русские колонтитулы, рекламу, типичные footer/support и повторяющиеся короткие строки из PDF-макетов.

## Что добавлено

### Модуль `services/preprocessing/cleaners/pdf_cleaner.py`

Функция **`clean_pdf_extracted_text`**: только для PDF-потока, вызывается в **`PreprocessingService`** после `PdfExtractor.extract` и до **`clean_extracted_text`**.

**Консервативные правила** (срабатывают только на **полную строку** после `strip`, без lowercasing всего документа; шаблоны с `re.IGNORECASE` где нужно):

- русские/английские варианты «страница N из M», «стр. N», `Page N of M`, короткие маркеры `- 3 -`;
- строки, начинающиеся с **`Footer noise`** (шаблон из ручной проверки);
- отдельная строка **`РЕКЛАМА`** / короткие `advertisement`, `sponsored content`, подписка;
- **«крошки»** только если в строке ≥ двух `>` и первый сегмент из белого списка (`home`, `главная`, `archive`, …);
- строка почти целиком из **URL** (короткая, без содержательного хвоста);
- **короткие** boilerplate support (`Technical support`, `Customer service`, `Contact us`, …) — только **полнострочные** совпадения с `$`, чтобы не задеть фразы вида «Contact us for preprocessing …».

Дополнительно: **схлопывание подряд идущих одинаковых коротких** непустых строк (длина ≤ 100 символов).

### `PdfExtractor`

Постранично оставлена только **нормализация пробелов/пустых строк**; шумовые шаблоны сосредоточены в `pdf_cleaner`, чтобы не дублировать логику.

## Почему это «консервативно»

- Не трогаем подстроки внутри длинных абзацев — только **целиком строку**.
- Нет глобального `lower()` текста документа.
- Support/реклама/навигация — узкие regex + длина для support.
- TXT/HTML ветки **не вызывают** `clean_pdf_extracted_text`.

## Изменения Documents UI

**Проблема:** дублировались «до / после» в блоке preprocessing и большой «Предпросмотр» съедал вертикальное место у чанков.

**Сделано:**

1. Убран второй столбец **«После»** (`preview_cleaned`) из preprocessing-блока.
2. Остался один блок **raw** (`preview_raw`) с подписью **«Preprocessing · до очистки (raw)»**.
3. Сетка preprocessing — **одна колонка** на всю ширину (класс `docs-preprocessing-previews__grid--single`).
4. Основной предпросмотр indexed text переведён на **`docs-panel-block__scroll--preview`** с **меньшим** `clamp` по высоте; чанки остаются на **`scroll--tall`**.

Файлы стилей и разметки: `DocumentsPage.tsx`, `globals.css`.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `services/preprocessing/cleaners/pdf_cleaner.py` | **Новый** — эвристики PDF после извлечения |
| `services/preprocessing/extractors/pdf_extractor.py` | Упрощён постраничный шаг (пробелы) |
| `services/preprocessing/preprocessing_service.py` | Вызов `clean_pdf_extracted_text` только для `.pdf` |
| `scripts/test_preprocessing_phase2_pdf_smoke.py` | Проверка `pdf_cleaner` + PDF-fixture при наличии PyMuPDF |
| `frontend/admin-ui/src/pages/DocumentsPage.tsx` | Один raw preprocessing preview; компактный scroll предпросмотра |
| `frontend/admin-ui/src/styles/globals.css` | `--preview`, `--single`, `--preproc-raw` |

## Команды тестов

```bash
python3 scripts/test_preprocessing_phase1_smoke.py
python3 scripts/test_preprocessing_phase2_pdf_smoke.py
```

При отсутствии PyMuPDF второй скрипт проверяет **`pdf_cleaner`** и завершается с сообщением о пропуске интеграционной части PDF.

## Ручной чеклист

1. Загрузить PDF с колонтитулами/рекламой — в indexed тексте (основной предпросмотр) шум заметно снижен.
2. Убедиться, что **raw** preprocessing показывает «грязный» текст, **Предпросмотр** — cleaned/indexed.
3. Блок **Чанки** виден ближе к первому экрану без длинного скролла.
4. TXT/HTML upload: регресс нет (содержимое не проходит `pdf_cleaner`).

## Не делалось (по границам задачи)

OCR, миграции БД, второй chunker, смена retrieval backend, массовый редизайн страницы Documents.
