# Engineering log: Documents UI — large document viewer (drawer)

**Дата:** 2026-05-12  
**Задача:** operational просмотр длинных текстов без «blackout» modal и исправление ширины RAW preprocessing.

## Выбранная архитектура viewer

**Правый drawer (фиксированная панель)** поверх страницы «Документы»:

- `position: fixed`, ширина `min(96vw, 1320px)`, высота на весь viewport;
- контент: read-only `<pre>` или `<textarea>` только в режиме редактирования canonical;
- **лёгкий scrim** (`rgba(15, 23, 42, 0.12)`) на весь экран — клик закрывает панель (если не идёт сохранение), без затемнения «как модальное окно на весь экран».

Почему **не** классический blocking modal:

- в operational сценарии нужно видеть контекст приложения (список документов, lifecycle, подсказки);
- тёмный fullscreen overlay мешает параллельно смотреть логи/статусы и отвлекает при частых открытиях.

Отказ от отдельного route и fullscreen takeover — по требованиям; Monaco/WYSIWYG/markdown не используются.

## RAW preprocessing — ширина

Корневая причина узкой колонки: в CSS **базовое** правило `.docs-preprocessing-previews__grid { grid-template-columns: 1fr 1fr; }` шло **после** модификатора `--single` с той же специфичностью, из‑за чего снова включались **два столбца**.

Исправление: селектор с цепочкой классов  
`.docs-preprocessing-previews__grid.docs-preprocessing-previews__grid--single { grid-template-columns: 1fr; }` **после** базового grid.

Дополнительно: блок RAW в **`docs-preprocessing-previews--bleed`** — отрицательные горизонтальные margin и `width: calc(100% + 0.96rem)` относительно padding summary, чтобы превью использовало **полную ширину карточки** документа.

## Разделение compact vs large layer

- Компактные высоты **Предпросмотр** и **чанков** не увеличивались.
- Редактирование canonical **убрано из карточки**; перенесено в drawer (кнопки «Открыть документ», «Редактировать», сохранение/отмена в footer drawer).

## Кнопки

| Зона | Кнопка | Действие |
|------|--------|----------|
| Preprocessing RAW | «Открыть RAW» | drawer, read-only, текст из `preview_raw` |
| Indexed предпросмотр | «Открыть документ» | drawer, загрузка `full_canonical_text`, read-only |
| Indexed предпросмотр | «Редактировать» | только при активной выбранной версии; загрузка полного текста, textarea в drawer |
| Внутри drawer (просмотр) | «Редактировать» | переход в режим правки без повторного fetch |

## Изменённые файлы

- `frontend/admin-ui/src/pages/DocumentsPage.tsx` — состояние viewer, кнопки, drawer, Escape, фокус textarea.
- `frontend/admin-ui/src/styles/globals.css` — grid fix, bleed, стили drawer/scrim, `docs-preview-head__actions`, удалены неиспользуемые стили компактного textarea.

## Чеклист ручной проверки

1. Документ с `preview_raw`: блок RAW на **всю ширину** карточки (одна колонка), компактная высота прежняя.
2. «Открыть RAW» — панель справа, текст скроллится, scrim светлый, список документов слабо виден через scrim.
3. «Открыть документ» — полный canonical в просмотре; «Редактировать» в шапке drawer переключает в правку.
4. «Редактировать» из карточки (активная версия) — сразу режим правки; сохранение создаёт версию и закрывает drawer; отмена/scrim/Esc закрывают без сохранения (кроме успешного save).
5. При смене документа или версии drawer закрывается.
6. Нет отдельного маршрута и нет полноэкранного чёрного overlay.
