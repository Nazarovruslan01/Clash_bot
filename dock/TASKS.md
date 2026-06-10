# CoC Bot — Задачи

_Обновлено: 2026-05-31_

---

## ✅ Выполнено

| ID | Что сделано |
|----|-------------|
| BUG-1 | `ASSIGN_BUILDER_APPRENTICE` → `ASSIGN_BUILDER_ASSISTANT` в `gui_server.py` |
| BUG-2 | Пауза через локальный GUI работает — `running()` проверяет локальный порт |
| BUG-3 | URL для `/status` и `/exclude` содержат `/{INSTANCE_ID}/` |
| BUG-4 | `send_notification()` отправляет уведомления в локальный GUI |
| BUG-5 | Debug `print()` в `upgrader.py` убран за `if configs.DEBUG` |
| REFACTOR-1 | Методы апгрейда унифицированы + дедупликация: `_open_upgrade_menu()` и `_make_item_locator()` вынесены, 4 метода сокращены с ~80–125 строк до ~45–95 строк (–61 строка) |
| REFACTOR-2 | Мёртвый код (`get_resources()`, `menu_ref_pos`) удалён |
| MINOR-1 | Debug print в `_home_lab_upgrade_once` заменён на `logger.debug` с контекстом |
| MINOR-2 | Голые `except: pass` в lab-upgrade циклах → `except Exception as e: logger.debug(...)` |
| FEAT-1 | Структурированное логирование: `logging` module, RotatingFileHandler (5MB, 3 backup), уровни DEBUG/INFO/WARNING/ERROR, формат `[HH:MM:SS] [INSTANCE] [LEVEL] msg` |
| FEAT-2 | Magic Items: авто-использование Builder / Research / Training Potion; управляется через GUI (`magic_items` exclusion) |
| ANTI-1 | Click position jitter: `_jitter()` — Gaussian noise σ=0.008, clamp [0.02, 0.98] — `click()`, `down()`, `multi_click()`, `swipe()`, `zoom()` |
| ANTI-2 | Inter-action delay randomization: `human_delay(base, spread=0.3)` — замена ~40 `time.sleep()` вызовов |
| ANTI-3 | CHECK_INTERVAL jitter: ±60с случайная вариация интервала проверки |
| ANTI-4 | Bezier curve swipes: cubic Bezier + случайные control points, ease-in/out timing, ±10% duration |
| ANTI-5 | Swipe speed variation: ease-in/out (3t²−2t³) + ±10% duration randomization |
| ANTI-6 | Deployment position variation: рандомизация центра деплоя (0.35–0.65 x, 0.70–0.85 y) + jittered card centers |
| ANTI-7 | Game state validation after recovery: `_validate_game_state()` — home/builder/loading/unknown |
| ANTI-8 | ADB dimension re-validation: предупреждение при несовпадении ADB_WINDOW_DIMS и WINDOW_DIMS |
| ANTI-9 | Minitouch health check: `health_check()` — no-op touch для верификации после `_recover()` |
| ANTI-10 | Research potion verification: уже реализовано в `upgrader.py` — ручное тестирование |
| ANTI-11 | Touch pressure variation: `_random_pressure()` — range 80–120, per-touch в `click()`, per-swipe |
| ANTI-12 | Session RNG seed: `Input_Handler.init_rng()` — воспроизводимое поведение через `SESSION_SEED` |
| ANTI-13 | Idle gestures: `idle_gesture()` — ~30% шанс micro-scroll между фазами |
| ANTI-14 | Screen edge avoidance: `_jitter()` clamp [0.02, 0.98] — автоматическое избежание краёв |
| FEAT-6 | GUI улучшения: уведомления (`GET /<id>/notifications`), Magic Items тогл, лог-вьювер (`GET /<id>/logs?n=60`), цветной статус-индикатор |

---

## 🔴 Баги (активные)

_Пока нет._

---

## 🟢 Следующие фичи (обсудить приоритет)

### FEAT-3: Clan Games — автозавершение заданий

**Проблема:** во время Clan Games бот просто продолжает штатную работу.

**Предложение:** детектировать активные Clan Games и выполнять задания (донаты, атаки, апгрейды) для накопления очков.

---

### FEAT-4: Улучшение стратегии атаки

**Проблема:** текущая атака — случайное размещение войск по позициям. Нет разделения между фармом ресурсов и толчком трофеев.

**Предложение:**
- режим `ATTACK_MODE = "farm" | "trophy"` в `configs.py`
- в режиме farm — атака баз с макс. ресурсами, сниженный порог поиска
- в режиме trophy — атака баз с макс. трофеями, более агрессивное размещение

---

### FEAT-5: Авто-донат войск в Клановый Замок

**Проблема:** бот не донатит войска сокланам.

**Предложение:** детектировать запрос в Клановый Замок → тренировать и донатить войска согласно конфигу.