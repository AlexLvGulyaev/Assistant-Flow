# Задача: подготовить ImageGen-промпты для AF Light/Dark preview

## Исходное задание

На основании выполненного исследования Assistant Flow (`2026-08-21_task-af-preview-light-dark-concept.md`) подготовить два production-ready ImageGen-промпта:

1. AF Preview Light — Concept 1 «Telegram RAG-диалог».
2. AF Preview Dark — Concept 3 «RAG-консоль и качество поиска».

Концепции не пересматривать, новые не предлагать. Использовать только фактически подтверждённые в исследовании функции, runtime-данные, тексты и показатели.

## Статус

completed

---

# Промпт 1: AF Preview Light — «Telegram RAG-диалог»

## Техническая рамка

- Aspect ratio: 16:9.
- Canvas: 1920 × 1080.
- Safe area: 12–15% left/right padding; main objects inside central 70–75%.
- Style: clean spatial scene, soft daylight, glass-morphic panels, restrained palette (white, pale blue-gray, soft violet accent for RAG flow).
- Render target: thumbnail-first, highly readable after strong downscale.

## Сцена

Центр композиции — крупная светлая панель Telegram-диалога, слегка повёрнутая в перспективе (не фронтально, угол ~12–15°). Панель похожа на современный мессенджер: белый фон, rounded corners, мягкая тень.

Слева внутри панели — user bubble с вопросом. Справа — assistant bubble с ответом. Между ними, за пределами панели, виден поток/луч, соединяющий вопрос с группой документов слева, и оттуда — к ответу. Документы — это стилизованные страницы/файлы с названием «company_regulations.txt» и другими типовыми именами корпоративных файлов. На документах мягко подсвечены фрагменты текста, чтобы показать, что ответ взят именно из них.

## Композиция

- Left third (inside safe zone): stack of 2–3 stylized document pages, slightly floating, with highlighted text fragments. Label above: small badge «База знаний».
- Center: large Telegram chat panel (45–50% of width), perspective-tilted. Inside:
  - Top bar: «Assistant Flow» + small status dot.
  - User bubble (left side, pale gray-blue): question.
  - Assistant bubble (right side, soft violet/blue): answer.
- Between documents and chat: 3–4 glowing particles/light fragments moving from documents toward the assistant bubble, symbolizing retrieved chunks.
- Right side: small vertical badge strip: «RAG mode», «Weaviate», «gpt-4o-mini». Each badge large enough to read.

## Текстовое содержимое

- User bubble (bold/semibold, large Cyrillic):
  «Что ты знаешь про ООО НоваТех?»
- Assistant bubble (medium, large Cyrillic, 3 short lines):
  «ООО «НоваТех» зарегистрировано 14 марта 2019 года. Компания находится в Казани, основная деятельность — разработка ПО.»
- Document stack label:
  «База знаний»
- Document filenames (small but still readable, 2 lines max):
  «company_regulations.txt»
  «employee_faq.txt»
- Right badges:
  «RAG»
  «Weaviate»
  «gpt-4o-mini»

## Запреты

- No generic AI brain, robots, humans, terminals, code walls, architecture diagrams, tiny UI cards, decorative AI abstraction.
- No fullscreen screenshot look.
- No text smaller than comfortably readable at thumbnail size.

## Ключевой визуальный тезис

Пользователь задаёт обычный вопрос в Telegram, а ответ приходит из корпоративной базы знаний — это видно по документам и потоку фрагментов к assistant bubble.

## Промпт для генератора (русский, структурированный)

```
Создай изображение 16:9, 1920×1080, thumbnail-first, высокая читаемость после уменьшения.

Светлая пространственная сцена: белый и мягкий голубо-серый фон, стеклянные/матовые панели.

В центре — крупная панель Telegram-диалога, слегка повёрнутая в перспективе (угол ~15°). Верхняя панелька с названием «Assistant Flow» и зелёной точкой статуса.

Слева внутри чата — большой user-bubble светло-серого цвета с жирным крупным текстом на русском:
«Что ты знаешь про ООО НоваТех?»

Справа — большой assistant-bubble мягкого фиолетово-голубого цвета с крупным русским текстом:
«ООО «НоваТех» зарегистрировано 14 марта 2019 года. Компания находится в Казани, основная деятельность — разработка ПО.»

Слева от панели чата — стопка из 2–3 стилизованных документов (листы А4), плавающих в воздухе. На верхнем документе видно имя файла «company_regulations.txt» и подсвеченные жёлтым фрагменты текста. Метка над документами: «База знаний».

Между документами и assistant-bubble — светящиеся частицы/линии, символизирующие найденные фрагменты, летящие к ответу.

Справа от чата — вертикальная полоса из 3 крупных badge'ов с читаемым русским/английским текстом:
«RAG»
«Weaviate»
«gpt-4o-mini»

Минимум объектов, крупные панели, много воздуха, короткие строки, высокий контраст, крупная кириллица. Без людей, роботов, мозгов, терминалов, диаграмм и мелких UI-карточек. Общий стиль — современный enterprise SaaS illustration.
```

---

# Промпт 2: AF Preview Dark — «RAG-консоль и качество поиска»

## Техническая рамка

- Aspect ratio: 16:9.
- Canvas: 1920 × 1080.
- Safe area: 12–15% left/right padding; main objects inside central 70–75%.
- Style: dark spatial scene, deep navy/black background, glass-morphic panels with subtle rim light, violet/cyan accent glows.
- Render target: thumbnail-first, highly readable after strong downscale.

## Сцена

Центр — крупная тёмная операторская панель (RAG observability console), слегка повёрнутая в перспективе (~12–15°). Панель разделена на три крупных зоны:
1. Верх: query + answer.
2. Центр: найденные чанки с relevance scores.
3. Низ/right strip: backend/model/faithfulness badges.

Слева от панели — вертикальный тонкий луч/поток, входящий в панель: это символизирует пользовательский вопрос из Light-сцены. Справа от панели — 3 больших стеклянных блока «chunk», каждый с текстовым фрагментом и яркой цифрой score.

## Композиция

- Left edge (inside safe zone): faint incoming light trail labeled «Вопрос пользователя».
- Center: large dark console panel (50–55% of width), perspective tilted.
  - Top section: header «RAG Observability», execution ID line (truncated but present), query line, answer line.
  - Middle section: 3 chunk cards in a slight arc or staggered row. Each card shows a short text fragment and a large score number.
- Right side: vertical stack of large metric badges:
  «Weaviate»
  «top_k = 3»
  «gpt-4o-mini»
  «faithfulness 0.9»

## Текстовое содержимое

- Header (bold, large Cyrillic):
  «RAG Observability»
- Subheader / query line (medium Cyrillic):
  «Запрос: Что ты знаешь про ООО НоваТех?»
- Answer line (medium Cyrillic, short):
  «Ответ из базы знаний»
- Chunk cards (3 cards):
  - Card 1: short fragment + large score «0.46»
  - Card 2: short fragment + large score «0.63»
  - Card 3: short fragment + large score «0.65»
  Fragment text can be placeholder like «...общество с ограниченной ответственностью...» but must stay readable.
- Right badges:
  «backend: Weaviate»
  «model: gpt-4o-mini»
  «top_k: 3»
  «faithfulness: 0.9»
- Incoming trail label:
  «Вопрос пользователя»

## Запреты

- No generic AI brain, robots, humans, terminals, code walls, architecture diagrams, tiny UI cards, decorative AI abstraction.
- No fullscreen screenshot look.
- No text smaller than comfortably readable at thumbnail size.
- Do not turn it into a dense dashboard with many small numbers.

## Ключевой визуальный тезис

Оператор видит не только ответ AI, но и как система его получила: найденные фрагменты документов, их relevance scores, retrieval backend и модель.

## Промпт для генератора (русский, структурированный)

```
Создай изображение 16:9, 1920×1080, thumbnail-first, высокая читаемость после уменьшения.

Тёмная пространственная сцена: глубокий тёмно-синий/чёрный фон, стеклянные панели с тонкой каймой-светом, фиолетовые и циановые акцентные свечения.

В центре — крупная тёмная операторская панель «RAG observability console», слегка повёрнутая в перспективе (угол ~15°). Верх панели: крупный жирный заголовок «RAG Observability» и под ним строка «Запрос: Что ты знаешь про ООО НоваТех?» крупным кириллическим текстом.

Внутри панели — три крупных стеклянных блока «chunk», расположенных дугой. Каждый блок содержит короткий текстовый фрагмент (например, «...общество с ограниченной ответственностью...») и крупное число score:
- «0.46»
- «0.63»
- «0.65»

Цифры score должны быть самыми крупными элементами в блоках, bold/semibold, светящиеся мягким фиолетово-голубым.

Справа от панели — вертикальная полоса из 4 крупных badge'ов с читаемым текстом:
«backend: Weaviate»
«model: gpt-4o-mini»
«top_k: 3»
«faithfulness: 0.9»

Слева от панели — тонкий светящийся луч/траектория с меткой «Вопрос пользователя», входящий в консоль.

Минимум объектов, крупные панели, много воздуха, короткие строки, высокий контраст, крупная кириллица. Без людей, роботов, мозгов, терминалов, диаграмм, плотных dashboard и мелких UI-карточек. Общий стиль — современная dark enterprise observability illustration.
```

---

# Сводная памятка для генерации

| Параметр | Light | Dark |
|---|---|---|
| Концепция | Telegram RAG-диалог | RAG observability console |
| Цветовая тема | Светлая, дневная | Тёмная, операторская |
| Ключевой объект | Telegram chat panel | RAG console panel |
| Вопрос | «Что ты знаешь про ООО НоваТех?» | «Запрос: Что ты знаешь про ООО НоваТех?» |
| Ответ | «ООО «НоваТех» зарегистрировано 14 марта 2019 года...» | — |
| Чанки / scores | Документы + поток фрагментов | 0.46 / 0.63 / 0.65 |
| Backend | Weaviate | Weaviate |
| Model | gpt-4o-mini | gpt-4o-mini |
| Metrics | RAG badge | top_k=3, faithfulness 0.9 |
| Общая грамматика | Пространственные панели, стекло, свет, минимум объектов | Та же, но тёмная |
