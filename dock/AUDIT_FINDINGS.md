# CoC Bot — Полный Code Audit

**Дата:** 15 июня 2026  
**Статус:** Завершено  
**Всего найдено:** 39+ проблем (8 CRITICAL, 11 MEDIUM, 7 HIGH, 13 LOW)

---

## Executive Summary

Проведён комплексный аудит всей кодовой базы бота (utils.py, coc_bot.py, upgrader.py, attacker.py, configs, GUI, Flask app). Выявлены **8 критических багов**, которые могут вызвать падение бота или некорректное поведение:

1. ❌ Свежая установка по шаблону падает с `AttributeError` (10 ключей конфига отсутствуют)
2. ❌ `coc_bot.py` — `NameError` при падении `start_coc()`
3. ❌ Gemini retry-цикл выходит после первой ошибки вместо 5 попыток
4. ❌ Атака падает на пустом экране (`ZeroDivisionError`)
5. ❌ Исключения из `detect_troop_positions` не перехватываются
6. ❌ Research Potion совсем не работает (мёртвый код)
7. ❌ Flask с `debug=True` на `0.0.0.0` (RCE уязвимость)
8. ❌ Wait-циклы съедают ошибки без логирования

---

## 🔴 CRITICAL Issues (8)

### C-1 · configs.template.py — 10 ключей отсутствуют
- **Файл:** `src/configs.template.py`
- **Проблема:** Свежий инстал → `AttributeError` сразу при старте
- **Отсутствуют:**
  - `CHECK_INTERVAL_JITTER`
  - `USE_AI_GAME_STATE`, `USE_AI_POPUP_DISMISS`, `USE_AI_ATTACK_ANALYSIS`, `USE_AI_MATCH_FILTER`
  - `USE_RESOURCE_CHECK`
  - `MIN_LOOT_GOLD`, `MIN_LOOT_ELIXIR`, `MIN_LOOT_DARK_ELIXIR`
  - `MAX_MATCH_SEARCHES`
- **Fix:** скопировать блок `# OPTIONAL: AI Features` из `configs.py`

---

### C-2 · coc_bot.py:265 — NameError: min_completion_time
- **Файл:** `src/coc_bot.py`, строка ~265
- **Проблема:** переменная объявляется внутри `if start_coc():`, но используется вне блока
- **Сценарий:** `start_coc()` возвращает `False` → `min(min_completion_time, ...)` → `NameError`
- **Fix:** `min_completion_time = None` перед циклом (строка ~193)

---

### C-3 · coc_bot.py:148–151 — retry-цикл выходит после первой ошибки
- **Файл:** `src/coc_bot.py`, строки 148–151
- **Проблема:** `break` на уровне тела `for`, вне `except`
- **Эффект:** цикл делает **1 попытку** вместо `max_retries=5`
- **Код:** 
  ```python
  for attempt in range(max_retries):
      try:
          ...
      except (KeyboardInterrupt, SystemExit): raise
      except Exception: pass
      break   # ← ВСЕ РАВНО выполняется
  ```
- **Fix:** перенести `break` внутрь `try` после успешного выполнения

---

### C-4 · attacker.py:160 — ZeroDivisionError на чёрном экране
- **Файл:** `src/attacker.py`, строка ~160
- **Проблема:**
  ```python
  profile = (profile - profile.min()) / (profile.max() - profile.min())
  ```
  На однородном кадре `max == min` → деление на ноль
- **Сценарий:** загрузочный экран, чёрный экран, пустой фрейм от ADB
- **Fix:** `denom = ...; ... / (denom if denom > 0 else 1)`

---

### C-5 · attacker.py:177, 184 — RuntimeError / AssertionError не перехвачены
- **Файл:** `src/attacker.py`, строки 177, 184, цикл деплоя (~383–406)
- **Проблема:** 
  - Строка 177: `RuntimeError` если нет gap между картами войск
  - Строка 184: `AssertionError` если нечётное число пиков
- **Эффект:** атака полностью прерывается, войска не деплоятся
- **Fix:** `try/except Exception` вокруг `detect_troop_positions`

---

### C-6 · upgrader.py:978–985 — Research Potion — мёртвый код
- **Файл:** `src/upgrader.py`, строки 978–985
- **Проблема:** `home_lab_available()` **всегда возвращает `True`**
- **Эффект:** ветка `if not lab_available:` никогда не выполняется, `USE_RESEARCH_POTION` не работает
- **Fix (вариант A):** реализовать реальную проверку занятости лаборатории  
  **Fix (вариант B):** добавить `# TODO: not implemented` и задокументировать ограничение

---

### C-7 · app/app.py:209 — Flask с debug=True на 0.0.0.0
- **Файл:** `app/app.py`, строка ~209
- **Проблема:**
  ```python
  app.run(host="0.0.0.0", port=1234, debug=True)
  ```
- **Уязвимость:** Werkzeug interactive debugger доступен из интернета → **RCE**
- **Fix:** `debug=False`; в production использовать только `wsgi.py`

---

### C-8 · attacker.py:453, 480 — except Exception: pass без логирования
- **Файл:** `src/attacker.py`, строки ~453, ~480
- **Проблема:** ADB-отключения в wait-циклах съедаются молча
- **Fix:** логировать: `logger.debug("wait loop error: %s", e)`

---

## 🟠 HIGH Issues (6)

### H-1 · 22+ bare `except:` вместо `except Exception:`
- **Файлы:** `utils.py` (22), `attacker.py`, `upgrader.py`
- **Проблема:** ловит `SystemExit`, `KeyboardInterrupt`, `MemoryError`
- **Наиболее опасные:**
  - `utils.py:500` — весь `start_coc()` молча возвращает `False` на **любой** ошибке
  - `utils.py:806` — OCR backoff на 10 мин без лога при **любой** ошибке
- **Fix:** заменить на `except Exception:`; для `utils.py:806` добавить логирование

---

### H-2 · utils.py:1348–1356 — TOCTOU race в get_frame
- **Файл:** `src/utils.py`, строки 1348–1356
- **Проблема:** проверка `cached_frame is not None` вне lock; два потока могут вызвать `ADB_DEVICE.screenshot()` одновременно
- **Fix:** перенести `with cls._frame_lock:` на весь метод

---

### H-3 · utils.py:1464–1466 — ThreadPoolExecutor double-init race
- **Файл:** `src/utils.py`, строки 1464–1466
- **Проблема:** два потока видят `pool is None` → оба создают `ThreadPoolExecutor` → один утекает
- **Fix:** инициализировать пул на уровне класса: `pool: ClassVar[ThreadPoolExecutor] = ThreadPoolExecutor()`

---

### H-4 · coc_bot.py:281–294 — exponential backoff сбрасывается
- **Файл:** `src/coc_bot.py`, строки 281–294
- **Проблема:** `_err_count` сбрасывается в 0 на каждом успешном recovery
- **Эффект:** мягкие сбои (ADB OK, игра вылетает) → задержка всегда 10 сек, не нарастает
- **Fix:** инкрементировать `_err_count` **перед** recovery; сбрасывать только на чистой итерации

---

### H-5 · attacker.py:66–73 — xys может быть unbound
- **Файл:** `src/attacker.py`, строки 66–73
- **Проблема:** если `Frame_Handler.locate` выбросит исключение на первом вызове, `xys` никогда не присваивается
- **Fix:** `xys = []` перед циклом

---

### H-6 · utils.py:321–323 — get_telegram_chat_id KeyError на не-message апдейтах
- **Файл:** `src/utils.py`, строки 321–323
- **Проблема:** Telegram возвращает `channel_post`, `callback_query` без ключа `"message"`
- **Fix:** фильтровать: `messages = [u for u in res["result"] if "message" in u]`

---

## MEDIUM Issues (5)

### M-1 · upgrader.py:960–965 — после max retries continue вместо break
- **Файл:** `src/upgrader.py`, строки 960–965
- **Проблема:** на исчерпание retries → `continue` вместо `break`
- **Эффект:** бот продолжает пробовать тот же апгрейд
- **Fix:** заменить `continue` на `break`

---

### M-2 · upgrader.py:971 — исключения не логируются в production
- **Файл:** `src/upgrader.py`, строка ~971
- **Проблема:**
  ```python
  except Exception as e:
      if configs.DEBUG: logger.debug(...)  # в production — молча
  ```
- **Fix:** `logger.warning(...)` безусловно

---

### M-3 · app/app.py — request.json без проверки на None (5 мест)
- **Файл:** `app/app.py`, строки ~115, 133, 145, 161, 180
- **Проблема:** запрос с неверным `Content-Type` → `request.json` = `None` → `AttributeError.get` → 500
- **Fix:** `request.get_json(silent=True) or {}`

---

### M-4 · gui.py:37 — pipe.recv() блокирует вечно
- **Файл:** `src/gui.py`, строка 37
- **Проблема:** если `gui_server` упал до отправки порта, главный процесс висит
- **Fix:** `if not self.pipe.poll(10): raise RuntimeError(...)`

---

### M-5 · gui_server.py:17 — wildcard import from configs import *
- **Файл:** `src/gui_server/gui_server.py`, строка 17
- **Проблема:** импорт всех переменных в глобальный namespace Flask
- **Эффект:** любое совпадение имён → молчаливый баг
- **Fix:** `import configs` + явные ссылки `configs.UPGRADE_HEROES`

---

## 🟡 LOW Issues (13)

| # | Файл / Строки | Проблема | Fix |
|---|---|---|---|
| L-1 | `utils.py:424,554` | Hardcoded scale range лодки `(0.43, 0.47, 0.01)` | → `configs.BOAT_ICON_SCALE_*` |
| L-2 | `utils.py:472,515,528` | CoC package name повторяется в 3 местах | → константа `COC_PACKAGE` |
| L-3 | `upgrader.py:84,87,91,94,228` | Hardcoded координаты кликов | → configs или Asset_Manager |
| L-4 | `attacker.py:166` | dist_categories для 1920×1080 захардкожены | → configs |
| L-5 | `attacker.py:428-429` | Hardcoded 11 слотов / 4 клика builder attack | → configs |
| L-6 | `upgrader.py:519,662,772,868` | `raw[:-3]` без комментария | Добавить комментарий |
| L-7 | `utils.py:1413 vs 1434` | `locate()`: `>= thresh` vs `> thresh` | Унифицировать |
| L-8 | `attacker.py:464,491` | Двойной лог ошибки в DEBUG | Убрать дублирование |
| L-9 | `app/wsgi.py:4` | `PYTHONANYWHERE_USERNAME = ""` | Валидация при старте |
| L-10 | `utils.py:606–615` | `require_exit` без `@functools.wraps` | Добавить wraps |
| L-11 | `utils.py:1476–1478` | APScheduler стартует при импорте | Перенести в явный `start()` |
| L-12 | `upgrader.py:480` | Fallback на Town Hall без лога | Добавить `logger.warning` |
| L-13 | `utils.py:1494–1496` | `optimal_template_font_size` → crash на пустом range | Добавить guard |

---

## Итоговая таблица по файлам

| Файл | CRITICAL | HIGH | MEDIUM | LOW | Всего |
|---|---|---|---|---|---|
| `src/configs.template.py` | 1 | - | - | - | 1 |
| `src/coc_bot.py` | 2 | - | 1 | - | 3 |
| `src/attacker.py` | 2 | 1 | 2 | 3 | 8 |
| `src/upgrader.py` | 1 | - | 2 | 4 | 7 |
| `src/utils.py` | - | 3 | 1 | 5 | 9 |
| `app/app.py` | 1 | - | 1 | - | 2 |
| `src/gui.py` | - | - | 1 | - | 1 |
| `src/gui_server.py` | - | - | 1 | - | 1 |
| `app/wsgi.py` | - | - | - | 1 | 1 |
| **ВСЕГО** | **8** | **4** | **9** | **13** | **34** |

---

## Рекомендуемый порядок исправлений

1. **C-1** — configs.template.py (5 мин)
2. **C-2, C-3** — coc_bot.py (10 мин)
3. **C-4, C-5** — attacker.py основные (15 мин)
4. **C-6** — upgrader.py research potion (5 мин)
5. **C-7, C-8** — app.py + attacker.py логирование (10 мин)
6. **M-1...M-5** — остальные серьёзные (30 мин)
7. **L-1...L-13** — технический долг (20 мин)

**Итого: ~1.5 часа на все исправления**

---

## Скрипты проверки

```bash
# Синтаксис
python3 -m py_compile src/*.py src/gui_server/*.py app/*.py && echo "✓ Syntax OK"

# Импорты
python3 -c "from src import utils, upgrader, attacker, coc_bot; print('✓ Imports OK')"

# Синхронизация конфигов
python3 -c "
import ast, sys
def get_keys(path):
    with open(path) as f: src = f.read()
    tree = ast.parse(src)
    return {t.targets[0].id for t in ast.walk(tree) 
            if isinstance(t, ast.Assign) and len(t.targets) == 1 
            and isinstance(t.targets[0], ast.Name)}
cfg = get_keys('src/configs.py')
tpl = get_keys('src/configs.template.py')
missing = cfg - tpl
print('MISSING:' if missing else '✓ SYNC OK', sorted(missing) if missing else '')
"
```
