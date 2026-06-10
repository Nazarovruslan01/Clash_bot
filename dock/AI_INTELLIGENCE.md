# AI Intelligence — Добавление мозгов боту

_Создан: 2026-06-10_

---

## Обзор

Бот сейчас работает по жёстким правилам: шаблонный матчинг, фиксированные приоритеты апгрейдов, случайная точка деплоя войск. Все три области можно значительно улучшить через Gemini Vision — он уже подключён для OCR, нужно только расширить его использование.

Три направления, каждое независимо реализуется:

---

## 1. Умная атака (Attack Intelligence)

### 1.1 Анализ вражеской базы перед деплоем

**Проблема сейчас:**
Войска деплоятся в случайный центр `(rng.uniform(0.35, 0.65), rng.uniform(0.70, 0.85))` без анализа базы противника. Атака не отличается в зависимости от того, что на экране.

**Что добавить: `analyze_enemy_base(frame) -> AttackPlan`**

Делаем один Gemini-запрос со скриншотом поля боя и промптом:

```
Analyze this Clash of Clans base screenshot.
Return JSON:
{
  "town_hall": {"x": 0.0-1.0, "y": 0.0-1.0} | null,
  "resource_cluster": {"x": 0.0-1.0, "y": 0.0-1.0},
  "recommended_deploy_x": 0.0-1.0,
  "recommended_deploy_y": 0.0-1.0,
  "base_type": "dead" | "active" | "engineered",
  "notes": "..."
}
Only output valid JSON.
```

Возвращаем `AttackPlan` dataclass. Используем `recommended_deploy_x/y` вместо рандомного центра в `deploy_troops`.

**Fallback:** если Gemini недоступен или JSON невалидный — текущее рандомное поведение.

---

### 1.2 Умный поиск матча (Match Filtering)

**Проблема сейчас:**
`start_normal_attack` берёт первый попавшийся матч без оценки ресурсов.

**Что добавить: `evaluate_match(frame) -> MatchScore`**

После нахождения противника, но до подтверждения атаки (`confirm_attack`) — снять скриншот и спросить Gemini:

```
This is a Clash of Clans enemy base preview.
Return JSON:
{
  "gold": estimated gold loot (int),
  "elixir": estimated elixir loot (int),
  "dark_elixir": estimated dark elixir loot (int),
  "skip": true/false
}
Only output valid JSON.
```

Логика:
- Если `skip=true` или суммарный лут < `MIN_LOOT_THRESHOLD` → нажать "Next" и искать следующий
- Максимум `MAX_MATCH_SEARCHES` попыток, потом атаковать что есть

**Новые конфиги:**
```python
MIN_LOOT_GOLD = 0
MIN_LOOT_ELIXIR = 0
MIN_LOOT_DARK_ELIXIR = 0
MAX_MATCH_SEARCHES = 5
USE_AI_MATCH_FILTER = False
```

---

### 1.3 Умный деплой по типу войск

**Проблема сейчас:**
Все типы войск (`troop`, `spell`, `clan`, `hero`) деплоятся в одну точку.

**Что добавить:**
На основе `AttackPlan` из 1.1:
- `hero` + `clan` → к ратуше / главной точке атаки
- `troop` (tanks/giants) → по периметру со стороны ресурсов
- `spell` → на скопление зданий / по пути войск

Реализация: расширить `deploy_troops` чтобы принимать `attack_plan: AttackPlan | None`. Если None — текущее поведение.

---

## 2. Умные апгрейды (Upgrade Intelligence)

### 2.1 Resource-aware upgrade selection

**Проблема сейчас:**
Бот пытается запустить апгрейд, кликает по нему, видит красный цвет цены — и уходит. Это цикл из N попыток впустую, особенно когда большинство апгрейдов дорогие.

**Что добавить: `get_home_resources() -> Resources`**

Перед циклом апгрейдов — читать ресурсы из топ-бара через OCR:

```python
@dataclass
class Resources:
    gold: int
    elixir: int
    dark_elixir: int
    builder_gold: int
    builder_elixir: int
```

Метод `get_home_resources()` читает секцию топ-бара через OCR. В `_home_upgrade_once` при priority-upgrade — сравнивать стоимость с ресурсами до клика. Если заведомо не хватает — пропустить и взять следующий приоритет.

---

### 2.2 Adaptive priority — автоматический downgrade

**Проблема сейчас:**
Если все апгрейды в priority level недоступны — бот пробует их все, каждый раз получая отказ, потом переходит к рандомному апгрейду.

**Что добавить:**
Хранить `last_failed_upgrades: dict[str, float]` (имя → timestamp) в памяти сессии. Не пытаться один и тот же апгрейд повторно до следующего CHECK_INTERVAL.

```python
logger.info("  [Home] Priority upgrades unavailable (resources/busy), falling back to random")
```

---

### 2.3 Upgrade completion detection

**Проблема сейчас:**
Бот не знает когда завершится текущий апгрейд — просто ждёт CHECK_INTERVAL и проверяет снова.

**Что добавить:**
После успешного запуска апгрейда — читать время завершения из UI через OCR:

```python
logger.info("  [Home] Cannon → Level 12, completes in ~4h")
```

Опционально: динамически подстраивать следующий CHECK_INTERVAL под минимальное время завершения апгрейдов.

---

## 3. Game State Intelligence

### 3.1 Gemini-based state recognition (fallback)

**Проблема сейчас:**
`_validate_game_state()` использует template matching. Ненадёжно на неожиданных экранах (диалоги, события, сезонные обновления).

**Что добавить: `gemini_game_state(frame) -> str`**

Один запрос Gemini как fallback когда template matching вернул "unknown":

```
What screen is this in Clash of Clans?
Reply with only one word: "home", "builder", "attack", "loading", "dialog", "unknown"
```

```python
def _validate_game_state(self):
    # ... текущая логика ...
    # если "unknown" — спросить Gemini
    if configs.GEMINI_API_KEY != "":
        frame = Frame_Handler.get_frame(grayscale=False)
        state = OCR_Handler.gemini_game_state(frame)
        if state in ("home", "builder", "loading"):
            return state
    return "unknown"
```

---

### 3.2 Event / popup detection

**Проблема сейчас:**
Сезонные события, Clan Games-баннеры, обновления игры — бот их не обрабатывает, теряется.

**Что добавить: `dismiss_popups()`**

Вызывать в начале каждого цикла после `start_coc()`:

```python
def dismiss_popups(self, max_attempts=5):
    """Dismiss unexpected dialogs/popups using Gemini vision."""
    for _ in range(max_attempts):
        frame = Frame_Handler.get_frame(grayscale=False)
        x, y = OCR_Handler.gemini_find_button(frame, "close or dismiss button")
        if x is None:
            break
        Input_Handler.click(x, y, jitter=False)
        human_delay(0.5)
```

`gemini_find_button(frame, description)` — новый метод в `OCR_Handler`:
```
In this Clash of Clans screenshot, find the "{description}".
Return JSON: {"x": 0.0-1.0, "y": 0.0-1.0} or {"x": null, "y": null} if not found.
```

---

## Архитектура изменений

### Новые методы

| Модуль | Метод | Описание |
|--------|-------|----------|
| `utils.py → OCR_Handler` | `gemini_game_state(frame)` | Определить экран через Gemini |
| `utils.py → OCR_Handler` | `gemini_find_button(frame, desc)` | Найти кнопку по описанию |
| `upgrader.py → Upgrader` | `get_home_resources()` | OCR ресурсов из топ-бара |
| `upgrader.py → Upgrader` | `get_builder_resources()` | OCR ресурсов билдер-базы |
| `attacker.py → Attacker` | `analyze_enemy_base(frame)` | Gemini-анализ вражеской базы |
| `attacker.py → Attacker` | `evaluate_match(frame)` | Оценить лут перед атакой |
| `coc_bot.py → CoC_Bot` | `dismiss_popups()` | Закрыть неожиданные диалоги |

### Новые конфиги

```python
# AI Features (все выключены по умолчанию)
USE_AI_ATTACK_ANALYSIS = False   # анализ вражеской базы перед деплоем
USE_AI_MATCH_FILTER = False      # фильтрация матчей по луту
USE_AI_POPUP_DISMISS = True      # автозакрытие попапов через Gemini
MIN_LOOT_GOLD = 0
MIN_LOOT_ELIXIR = 0
MIN_LOOT_DARK_ELIXIR = 0
MAX_MATCH_SEARCHES = 5
```

Все AI-фичи выключены по умолчанию. Включаются независимо. Требуют `GEMINI_API_KEY != ""`.

---

## Порядок реализации (приоритет)

| # | Фича | Сложность | Impact |
|---|------|-----------|--------|
| 1 | `dismiss_popups` (3.2) | низкая | высокий — бот перестанет зависать на ивентах |
| 2 | `gemini_game_state` fallback (3.1) | низкая | высокий — надёжнее recovery |
| 3 | `get_home/builder_resources` (2.1) | средняя | средний — меньше холостых попыток |
| 4 | `analyze_enemy_base` (1.1) | средняя | высокий — умная атака |
| 5 | `evaluate_match` (1.2) | средняя | средний — больше лута за атаку |
| 6 | Upgrade completion detection (2.3) | средняя | средний — динамический интервал |
| 7 | Умный деплой по типу войск (1.3) | высокая | средний — требует точной работы 1.1 |
| 8 | Adaptive priority (2.2) | высокая | средний — сложная логика сессии |
