# CoC Bot — Задачи

_Обновлено: 2026-05-30_  (FEAT-2 ✅, FEAT-6 в работе)

---

## ✅ Выполнено

| ID | Что сделано |
|----|-------------|
| BUG-1 | `ASSIGN_BUILDER_APPRENTICE` → `ASSIGN_BUILDER_ASSISTANT` в `gui_server.py` |
| BUG-2 | Пауза через локальный GUI работает — `running()` проверяет локальный порт |
| BUG-3 | URL для `/status` и `/exclude` содержат `/{INSTANCE_ID}/` |
| BUG-4 | `send_notification()` отправляет уведомления в локальный GUI |
| BUG-5 | Debug `print()` в `upgrader.py` убран за `if configs.DEBUG` |
| REFACTOR-1 | Методы апгрейда унифицированы: `_home_upgrade_once`, `_home_lab_upgrade_once`, `_builder_upgrade_once`, `_builder_lab_upgrade_once` |
| REFACTOR-2 | Мёртвый код (`get_resources()`, `menu_ref_pos`) удалён |
| MINOR-1 | Debug print в `_home_lab_upgrade_once` заменён на `logger.debug` с контекстом |
| MINOR-2 | Голые `except: pass` в lab-upgrade циклах → `except Exception as e: logger.debug(...)` |
| FEAT-1 | Структурированное логирование: `logging` module, RotatingFileHandler (5MB, 3 backup), уровни DEBUG/INFO/WARNING/ERROR, формат `[HH:MM:SS] [INSTANCE] [LEVEL] msg` |
| FEAT-2 | Magic Items: авто-использование Builder / Research / Training Potion; управляется через GUI (`magic_items` exclusion) |

---

## 🔴 Баги (активные)

_Пока нет._

---

## 🟢 Следующие фичи (обсудить приоритет)

### FEAT-6: GUI — улучшения интерфейса

**Задачи:**

1. **Уведомления** — панель уже закодирована, но закомментирована. Включить + добавить `GET /<id>/notifications` в `gui_server.py`
2. **Magic Items тогл** — добавить переключатель `magic_items` в Task Settings (управление FEAT-2 из GUI)
3. **Лог-вьювер** — новая секция "Logs ▼" в GUI, читает `debug/{id}.log` через `GET /<id>/logs?n=60` (новый эндпоинт)
4. **Визуал / UX** — цветной статус-индикатор (точка: зелёная / жёлтая / красная) рядом с "Running…"

**Файлы:**
- `src/gui_server/gui_server.py` — +2 эндпоинта
- `src/gui_server/templates/instance.html` — раскомментировать уведомления, добавить тогл, лог-вьювер, точку
- `src/gui_server/static/styles.css` — стили для новых элементов

---

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
