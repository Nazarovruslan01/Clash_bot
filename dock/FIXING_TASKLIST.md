# 🔧 Таск-лист для исправления

Статусы: `[ ]` не начато · `[~]` в работе · `[x]` готово

---

## 🔴 CRITICAL (блокирующие) — должны быть исправлены первыми

### C-1 · configs.template.py — добавить 10 ключей

```
[ ] Добавить в src/configs.template.py:
   [ ] CHECK_INTERVAL_JITTER
   [ ] USE_AI_GAME_STATE
   [ ] USE_AI_POPUP_DISMISS
   [ ] USE_AI_ATTACK_ANALYSIS
   [ ] USE_AI_MATCH_FILTER
   [ ] USE_RESOURCE_CHECK
   [ ] MIN_LOOT_GOLD
   [ ] MIN_LOOT_ELIXIR
   [ ] MIN_LOOT_DARK_ELIXIR
   [ ] MAX_MATCH_SEARCHES
[ ] Проверить синхронизацию: python3 -c "import ast, sys; ..." (см. AUDIT_FINDINGS.md)
```

**Метка в коде:** "# OPTIONAL: AI Features" в configs.py

---

### C-2 · coc_bot.py:265 — инициализировать min_completion_time

```
[ ] Найти: строка ~193 (while True:)
[ ] Добавить перед циклом: min_completion_time = None
[ ] Проверить использования:
   [ ] Строка 265: min(min_completion_time, ...) должна обработать None
   [ ] Строка 266: использование переменной
```

**Проверка:** `python3 src/coc_bot.py` не должна выдать `NameError` при `start_coc() = False`

---

### C-3 · coc_bot.py:148–151 — исправить retry-цикл Gemini

```
[ ] Найти _validate_game_state() метод
[ ] Структура:
    for attempt in range(max_retries):
        try:
            ... do something ...
            break   # ← ДОЛЖНО быть здесь (при успехе)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass        # ← try again
    # break должен быть ВНУТРИ try, не снаружи

[ ] Переместить break внутрь try, после успешного выполнения
[ ] Убедиться что цикл повторяется несколько раз при ошибках
```

**Проверка:** при `gemini_game_state()` = None, цикл должен повторяться (до 5 попыток по коду)

---

### C-4 · attacker.py:160 — защита от ZeroDivisionError

```
[ ] Найти строку ~160 в complete_normal_attack
[ ] Текущий код:
    profile = (profile - profile.min()) / (profile.max() - profile.min())

[ ] Изменить на:
    denom = profile.max() - profile.min()
    if denom > 0:
        profile = (profile - profile.min()) / denom
    else:
        # uniform frame, skip this processing
        profile = profile  # или другая логика

[ ] Или одной строкой:
    profile = (profile - profile.min()) / max(profile.max() - profile.min(), 1)
```

**Проверка:** функция не должна выбросить ZeroDivisionError на чёрном/пустом экране

---

### C-5 · attacker.py:177, 184 — добавить try/except для detect_troop_positions

```
[ ] Найти вызовы detect_troop_positions в complete_normal_attack (цикл деплоя)
[ ] Обернуть в try/except:

    try:
        card_centers, card_types, card_counts = self.detect_troop_positions(frame)
    except RuntimeError as e:
        logger.warning("No card gap detected: %s", e)
        break  # или continue, в зависимости от логики
    except AssertionError as e:
        logger.warning("Invalid peaks detected: %s", e)
        break
    except Exception as e:
        logger.warning("detect_troop_positions failed: %s", e)
        break

[ ] Решить поведение: break (прекратить атаку) или continue (пропустить кадр)?
```

**Проверка:** трой-бар при странных картинках не должен завалить весь деплой

---

### C-6 · upgrader.py:978–985 — Research Potion

```
Два варианта на выбор:

ВАРИАНТ A (правильный):
[ ] Реализовать реальную проверку занятости лаборатории
    [ ] Добавить template matching или Gemini Vision для проверки занятости лаба
    [ ] Заменить возврат True на реальное значение
    [ ] Протестировать USE_RESEARCH_POTION = True

ВАРИАНТ B (временный):
[ ] Добавить комментарий в home_lab_available():
    # TODO: not implemented, always returns True — USE_RESEARCH_POTION will not work
[ ] Добавить комментарий в CLAUDE.md: "Research Potion не реализовано"
```

**Выбор:** какой вариант? Или можно оставить как "TODO"?

---

### C-7 · app/app.py:209 — убрать debug=True

```
[ ] Найти строку ~209: app.run(...)
[ ] Текущий код:
    app.run(host="0.0.0.0", port=1234, debug=True)

[ ] Изменить на:
    app.run(host="0.0.0.0", port=1234, debug=False)

[ ] Убедиться что в production (wsgi.py) также нет debug=True
```

**Проверка:** Werkzeug debugger должен быть недоступен

---

### C-8 · attacker.py:453, 480 — добавить логирование в wait-циклы

```
[ ] Найти строку ~453: except Exception: pass
[ ] Изменить на:
    except Exception as e:
        logger.debug("wait loop error (base detection): %s", e)

[ ] Найти строку ~480: except Exception: pass
[ ] Изменить на:
    except Exception as e:
        logger.debug("wait loop error (builder base): %s", e)
```

**Проверка:** при ADB-ошибке в wait-цикле должна быть запись в лог

---

## 🟠 HIGH/MEDIUM Issues

### M-1 · bare except → except Exception (22+ мест)

```
[ ] Файл: src/utils.py

Найти все "except:" (bare) и заменить на "except Exception:"
Особое внимание:

[ ] Строка ~500 (start_coc):
    except Exception as e:
        logger.error("Failed to start CoC after 120s: %s", e)
        return False

[ ] Строка ~806 (OCR_Handler.get_text):
    except Exception as e:
        logger.warning("Gemini OCR failed, falling back for 10 min: %s", e)
        cls.backoff_time = time.time() + 600

[ ] Все остальные 20 мест: просто заменить на except Exception:
```

**Проверка:** `grep "except:" src/utils.py` должен быть пуст или показать только нужные

---

### M-2 · utils.py:1464–1466 — ThreadPoolExecutor инициализация

```
[ ] Найти class Template_Matcher (строка ~1460)
[ ] Текущий код:
    if cls.pool is None:
        cls.pool = ThreadPoolExecutor()

[ ] Заменить на инициализацию на уровне класса:
    from typing import ClassVar
    
    class Template_Matcher:
        pool: ClassVar[ThreadPoolExecutor] = ThreadPoolExecutor()

[ ] Убрать ленивую инициализацию из batch_locate()
```

**Проверка:** параллельные вызовы `batch_locate` не должны создавать несколько пулов

---

### M-3 · coc_bot.py:281–294 — exponential backoff

```
[ ] Найти main loop (~281–294)
[ ] Текущая логика:
    _err_count = 0  # <- при старте
    while True:
        try:
            if not start_coc(): continue
            ...
        except Exception:
            delay = min(10 * 2 ** _err_count, 300)
            _err_count += 1
            time.sleep(delay)
            _recover()
            _err_count = 0  # ← ПРОБЛЕМА: сбрасывается тут

[ ] ПРАВИЛЬНАЯ логика:
    _err_count = 0
    while True:
        _err_count += 1  # ← инкрементировать ПЕРЕД попыткой
        try:
            if not start_coc(): 
                continue  # не сбрасывать счётчик
            ... main work ...
            _err_count = 0  # ← сбросить только при успехе полной итерации
        except Exception:
            delay = min(10 * 2 ** _err_count, 300)
            time.sleep(delay)
            _recover()
            # не сбрасывать здесь!
```

**Проверка:** при мягких сбоях (вечные перезапуски) задержка должна расти

---

### M-4 · attacker.py:66–73 — инициализировать xys

```
[ ] Найти find_a_match() или похожий метод
[ ] Текущий код:
    for _ in range(20):
        human_delay(0.5)
        xys = Frame_Handler.locate(...)
        if len(xys) > 0: break

[ ] Добавить перед циклом:
    xys = []
    for _ in range(20):
        human_delay(0.5)
        try:
            xys = Frame_Handler.locate(...)
        except Exception as e:
            logger.debug("locate error: %s", e)
            continue
        if len(xys) > 0: break
```

**Проверка:** функция не должна выбросить UnboundLocalError

---

### M-5 · upgrader.py:960–965 — replace continue with break

```
[ ] Найти max retries loop (строка ~960)
[ ] Текущий код:
    if retry_count >= _MAX_UPGRADE_RETRIES:
        retry_count = 0
        continue  # ← НЕПРАВИЛЬНО

[ ] Изменить на:
    if retry_count >= _MAX_UPGRADE_RETRIES:
        retry_count = 0
        break  # ← выйти из цикла

[ ] Убедиться что upgrade не пробуется больше нужного раза
```

---

### M-6 · upgrader.py:971 — логирование исключений

```
[ ] Найти upgrade loop (строка ~971)
[ ] Текущий код:
    except Exception as e:
        if configs.DEBUG: logger.debug("run_home_base: %s", e)

[ ] Изменить на:
    except Exception as e:
        logger.warning("run_home_base upgrade loop error: %s", e)

[ ] Убрать условие DEBUG
```

---

### M-7 · utils.py:321–323 — Telegram chat_id фильтрация

```
[ ] Найти get_telegram_chat_id()
[ ] Текущий код:
    chat_id = res["result"][-1]["message"]["chat"]["id"]

[ ] Изменить на:
    messages = [u for u in res["result"] if "message" in u]
    if not messages:
        raise RuntimeError("No messages in Telegram updates")
    chat_id = messages[-1]["message"]["chat"]["id"]

[ ] Убедиться что channel_post, callback_query не вызывают KeyError
```

---

### M-8 · app/app.py — request.json на 5 строках

```
[ ] Строка ~115:
    # Сейчас: data = request.json.get("time", 0)
    # Должно быть: data = request.get_json(silent=True) or {}; time_val = data.get("time", 0)

[ ] Строка ~133:
    # Сейчас: data = request.json
    # Должно быть: data = request.get_json(silent=True) or {}

[ ] Строка ~145:
    # Сейчас: data = request.json
    # Должно быть: data = request.get_json(silent=True) or {}

[ ] Строка ~161:
    # Сейчас: data = request.json
    # Должно быть: data = request.get_json(silent=True) or {}

[ ] Строка ~180:
    # Сейчас: data = request.json
    # Должно быть: data = request.get_json(silent=True) or {}
```

---

### M-9 · gui.py:37 — pipe.recv() с таймаутом

```
[ ] Найти __init__ метод GUI класса (строка ~37)
[ ] Текущий код:
    self.server_port = self.pipe.recv()

[ ] Изменить на:
    if not self.pipe.poll(timeout=10):
        raise RuntimeError("GUI server did not send port within 10 seconds")
    self.server_port = self.pipe.recv()
```

---

### M-10 · gui_server.py:17 — убрать wildcard import

```
[ ] Найти строку ~17 в src/gui_server/gui_server.py
[ ] Текущий код:
    from configs import *

[ ] Заменить на:
    import configs

[ ] Во всех местах где используются переменные конфига, заменить:
    UPGRADE_HOME_BASE  →  configs.UPGRADE_HOME_BASE
    GEMINI_API_KEY     →  configs.GEMINI_API_KEY
    и т.д.
```

**Проверка:** `grep "^[A-Z_]* =" src/gui_server/gui_server.py` не должен найти неожиданные переменные

---

### M-11 · upgrader.py:480 — логирование Town Hall fallback

```
[ ] Найти строку ~480 в run_home_base
[ ] Найти код который кликает на Town Hall как fallback
[ ] Добавить:
    logger.warning("No upgrade row found, falling back to Town Hall upgrade")
    Input_Handler.click(x_town_hall, y_town_hall)
```

---

## 🟡 LOW Issues (технический долг)

### L-1 · Hardcoded значения вынести в конфиг

```
[ ] utils.py:424, 554 — scale range лодки
    np.arange(0.43, 0.47, 0.01)
    → Добавить в configs.py: 
       BOAT_ICON_SCALE_MIN = 0.43
       BOAT_ICON_SCALE_MAX = 0.47
       BOAT_ICON_SCALE_STEP = 0.01

[ ] utils.py:472, 515, 528 — CoC package name
    "com.supercell.clashofclans"
    → Добавить в configs.py:
       COC_PACKAGE_NAME = "com.supercell.clashofclans"

[ ] upgrader.py:84, 87, 91, 94, 228 — координаты кликов
    Input_Handler.click(0.42, 0.05)  # home builders
    → Создать группу констант или в configs:
       HOME_BUILDERS_COORD = (0.42, 0.05)
       HOME_LAB_COORD = (0.41, 0.05)
       и т.д.

[ ] attacker.py:166 — dist_categories
    dist_categories = np.array([0.007, 0.015, 0.068])
    → Добавить в configs с комментарием (1920x1080 only)

[ ] attacker.py:428-429 — builder attack slots/clicks
    Hardcoded 11 и 4
    → BUILDER_ATTACK_SLOTS = 11
       BUILDER_ATTACK_CLICKS_PER_SLOT = 4
```

---

### L-2 · Комментарии к неочевидному коду

```
[ ] upgrader.py:519, 662, 772, 868 — raw[:-3]
    Добавить комментарий почему обрезаются последние 3 символа
    # Strip 3-char UI suffix from OCR result (e.g., "Iron Mine🔄" → "Iron Mine")
    raw = raw[:-3].strip() if len(raw) > 3 else raw
```

---

### L-3 · utils.py:1413 vs 1434 — унифицировать threshold

```
[ ] Найти locate() метод
[ ] Текущий код использует:
    return_all=True: np.where(res >= thresh)
    return_all=False: if max_val > thresh
    
[ ] Унифицировать на >= везде:
    np.where(res >= thresh)
    if max_val >= thresh
```

---

### L-4 · attacker.py:464, 491 — дублирование логирования

```
[ ] Найти except Exception блоки
[ ] Убрать дублирующий logger.debug в DEBUG режиме
[ ] Или унифицировать:
    logger.error("Home: Attack error: %s", e)
    # (no debug duplicate)
```

---

### L-5 · app/wsgi.py:4 — валидация при старте

```
[ ] Добавить в start Flask:
    PYTHONANYWHERE_USERNAME = ""
    if not PYTHONANYWHERE_USERNAME:
        raise RuntimeError("PYTHONANYWHERE_USERNAME is not configured in wsgi.py")
```

---

### L-6 · utils.py:606–615 — @functools.wraps

```
[ ] Найти require_exit decorator
[ ] Добавить:
    from functools import wraps
    
    def require_exit(n=1, delay=0.5):
        def decorator(func):
            @wraps(func)  # ← добавить
            def wrapper(*args, **kwargs):
                ...
            return wrapper
        return decorator
```

---

### L-7 · utils.py:1476–1478 — отложить APScheduler

```
[ ] Найти class Scheduler
[ ] Текущий код:
    class Scheduler:
        scheduler = BackgroundScheduler()
        scheduler.start()  # ← на уровне класса

[ ] Изменить на:
    class Scheduler:
        scheduler: Optional[BackgroundScheduler] = None
        
        @classmethod
        def start(cls):
            if cls.scheduler is None:
                cls.scheduler = BackgroundScheduler()
                cls.scheduler.start()

[ ] Вызвать Scheduler.start() из coc_bot.py.__init__()
```

---

## 📋 Проверочный список перед коммитом

```bash
# 1. Синтаксис
[ ] python3 -m py_compile src/*.py src/gui_server/*.py app/*.py

# 2. Импорты
[ ] python3 -c "from src import utils, upgrader, attacker, coc_bot; print('✓')"

# 3. Синхронизация конфигов
[ ] python3 << 'EOF'
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
if missing:
    print("MISSING:", sorted(missing)); sys.exit(1)
else: print("✓ configs in sync")
EOF

# 4. Нет bare except (кроме намеренных)
[ ] grep -n "except:" src/*.py | grep -v "except Exception:" | wc -l
    # Должно быть 0 или только намеренные случаи

# 5. Нет debug=True в production
[ ] grep -i "debug=True" app/*.py src/*.py
    # Не должно быть совсем
```

---

## Рекомендуемая последовательность

**День 1 — CRITICAL (все 8 проблем):** ~1 час
- C-1: configs.template.py (5 мин)
- C-2: coc_bot.py NameError (5 мин)
- C-3: coc_bot.py retry (10 мин)
- C-4: attacker.py ZeroDivision (10 мин)
- C-5: attacker.py detect_troop (10 мин)
- C-6: upgrader.py research potion (10 мин)
- C-7: app.py debug=True (5 мин)
- C-8: attacker.py logging (5 мин)

**День 2 — MEDIUM/HIGH (11 проблем):** ~1 час
- M-1–M-11: все (60 мин)

**День 3 — LOW (технический долг):** ~30 мин
- L-1–L-7: по желанию

**Итого:** ~2.5 часа полной разработки + тестирование
