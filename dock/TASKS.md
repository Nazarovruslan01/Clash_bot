# CoC Bot — Задачи: фиксы и рефакторинг

---

## 🔴 Баги (критические)

---

### BUG-1: `NameError` при старте локального GUI

**Файл:** `src/gui_server/gui_server.py:35`

**Проблема:**
```python
task_settings = {
    ...
    "builder_apprentice": not ASSIGN_BUILDER_APPRENTICE,  # ← переменной не существует
    ...
}
```
В `configs.template.py` переменная называется `ASSIGN_BUILDER_ASSISTANT`, а не `ASSIGN_BUILDER_APPRENTICE`.
При запуске с `--gui` сервер падает с `NameError: name 'ASSIGN_BUILDER_APPRENTICE' is not defined`.

**Фикс:**
```python
"builder_apprentice": not ASSIGN_BUILDER_ASSISTANT,
```

---

### BUG-2: Пауза не работает в режиме локального GUI

**Файл:** `src/utils.py:114-128`

**Проблема:**
```python
def running():
    if WEB_APP_URL == "": return True  # ← всегда True если нет внешнего web app
    try:
        response = requests.get(f"{WEB_APP_URL}/{INSTANCE_ID}/running", ...)
        ...
```
Когда бот запускается только с локальным GUI (без `WEB_APP_URL`), `running()` всегда возвращает `True`.
Кнопка "Pause" в GUI-окне устанавливает `end_time` у своего экземпляра `Instance`, но бот это значение никогда не читает.
В итоге: пауза через локальное окно не останавливает бота.

**Фикс:**
Добавить проверку локального GUI-сервера, если `WEB_APP_URL` не задан:
```python
def running():
    import requests
    from gui import get_gui

    if WEB_APP_URL != "":
        try:
            response = requests.get(
                f"{WEB_APP_URL}/{INSTANCE_ID}/running",
                timeout=(1, 2)
            )
            if response.status_code == 200:
                return response.json().get("running", False)
            return False
        except Exception as e:
            if configs.DEBUG: print("running", e)
            return False

    if get_gui() is not None:
        try:
            response = requests.get(
                f"http://localhost:{get_gui().server_port}/{INSTANCE_ID}/running",
                timeout=(1, 2)
            )
            if response.status_code == 200:
                return response.json().get("running", False)
            return True
        except Exception as e:
            if configs.DEBUG: print("running (local gui)", e)
            return True

    return True
```

---

### BUG-3: Неправильные URL при обращении к локальному GUI-серверу

**Файлы:** `src/coc_bot.py:31-41`, `src/utils.py:590-598`

**Проблема:**
Бот отправляет запросы на `/status` и `/exclude`, но GUI-сервер регистрирует маршруты как `/<id>/status` и `/<id>/exclude`.

`coc_bot.py`:
```python
requests.post(
    f"http://localhost:{get_gui().server_port}/status",  # ← нет /<id>/
    json={"status": status},
    ...
)
```

`utils.py` (Task_Handler.get_exclusions):
```python
res = requests.get(
    f"http://localhost:{get_gui().server_port}/exclude",  # ← нет /<id>/
    ...
)
```

**Следствие:**
- Статус бота не обновляется в локальном окне (всегда пусто).
- Настройки исключений из GUI игнорируются — бот апгрейдит всё подряд, даже если отключено.

**Фикс в `coc_bot.py`:**
```python
requests.post(
    f"http://localhost:{get_gui().server_port}/{utils.INSTANCE_ID}/status",
    json={"status": status},
    ...
)
```

**Фикс в `utils.py`:**
```python
res = requests.get(
    f"http://localhost:{get_gui().server_port}/{INSTANCE_ID}/exclude",
    ...
)
```

---

## 🟡 Баги (некритические)

---

### BUG-4: Уведомления не работают в локальном GUI

**Файл:** `src/gui_server/gui_server.py`

**Проблема:**
В `utils.py::send_notification()` уведомления отправляются только на `WEB_APP_URL`.
Локальный GUI-сервер не имеет маршрутов `/notify` и `/notifications`, поэтому при работе без внешнего веб-приложения уведомления о начатых апгрейдах не попадают в GUI-окно вообще.

**Фикс:**
1. Добавить в `gui_server.py` хранилище уведомлений в класс `Instance`:
```python
from collections import deque

NOTIFICATION_CACHE_SIZE = 3

class Instance:
    def __init__(self, id=None):
        ...
        self.notifications = deque(maxlen=NOTIFICATION_CACHE_SIZE)
```

2. Добавить два маршрута в `gui_server.py`:
```python
@app.route("/<id>/notify", methods=["POST"])
def handle_notify(id):
    import time
    instance = instances.get(id)
    if not instance: abort(404)
    data = request.json
    instance.notifications.append({"time_stamp": time.time(), "data": str(data)})
    return jsonify({"status": "success", "received": data})

@app.route("/<id>/notifications", methods=["POST"])
def handle_notifications(id):
    n = request.json
    instance = instances.get(id)
    if not instance: abort(404)
    return jsonify(list(instance.notifications)[-n:])
```

3. Расширить `send_notification()` в `utils.py`:
```python
def send_notification(text):
    import requests
    from gui import get_gui

    if WEB_APP_URL != "":
        try:
            requests.post(f"{WEB_APP_URL}/{INSTANCE_ID}/notify", json=text, timeout=(1, 2))
        except (KeyboardInterrupt, SystemExit): raise
        except: pass

    if get_gui() is not None:
        try:
            requests.post(
                f"http://localhost:{get_gui().server_port}/{INSTANCE_ID}/notify",
                json=text,
                timeout=(1, 2)
            )
        except (KeyboardInterrupt, SystemExit): raise
        except: pass

    if TELEGRAM_BOT_TOKEN != "":
        ...  # без изменений
```

---

### BUG-5: Debug `print()` оставлен в продакшн-коде

**Файл:** `src/upgrader.py:599`

```python
print(menu_left, x, menu_right, y)  # ← мусорный вывод в консоль
```

**Фикс:** Удалить строку, или заменить на:
```python
if configs.DEBUG: print("home_lab_specified_upgrade loc:", menu_left, x, menu_right, y)
```

---

## 🟢 Рефакторинг

---

### REFACTOR-1: Дублирование методов апгрейда в `Upgrader`

**Файл:** `src/upgrader.py`

**Проблема:**
Четыре пары методов делают почти одно и то же:

| Метод | Чем отличается |
|-------|---------------|
| `home_random_upgrade` | кнопка builders, шаблон героев |
| `home_lab_random_upgrade` | кнопка lab |
| `builder_random_upgrade` | кнопка builder_builders, другой confirm |
| `builder_lab_random_upgrade` | кнопка builder_lab, другой confirm |

Аналогично для `*_specified_upgrade`.

**Подход к рефакторингу:**
Вынести общую логику в приватный `_random_upgrade(config)` и `_specified_upgrade(config, upgrade_text)`, где `config` — dataclass или словарь с параметрами:

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class UpgradeConfig:
    open_menu: Callable          # функция открытия меню (click builders/lab)
    confirm_fn: Callable         # функция поиска кнопки подтверждения
    exclude_heroes: bool = False # нужно ли исключать героев
    log_prefix: str = ""         # для отладки
```

Каждый высокоуровневый метод (`home_upgrade`, `home_lab_upgrade`, etc.) передаёт свой `UpgradeConfig` в общую реализацию.
Это сокращает `upgrader.py` примерно с 1050 до ~600 строк без потери функциональности.

**Важно:** рефакторинг только после того, как все баги исправлены и проверены.

---

### REFACTOR-2: Убрать неиспользуемый код

**Файл:** `src/upgrader.py`

1. **`get_resources()`** — метод определён, нигде не вызывается. Удалить.

2. **`menu_ref_pos`** — вычисляется в 4 методах (`home_specified_upgrade`, `home_lab_specified_upgrade`, `builder_specified_upgrade`, `builder_lab_specified_upgrade`), но нигде не используется:
```python
if y_other is not None: menu_ref_pos = y_other  # присваивается...
else: menu_ref_pos = y_sug                        # ...и больше не используется
```
Удалить эти строки.

---

### REFACTOR-3: Консистентность импортов

**Файлы:** все в `src/`

**Проблема:**
Большинство `import` сделаны внутри методов:
```python
def some_method(self):
    import time, cv2, numpy as np
    ...
```
Это нестандартно и ухудшает читаемость. Объяснение: вероятно, чтобы ускорить запуск или избежать circular imports при сборке PyInstaller.

**Решение:** не трогать — паттерн, по всей видимости, намеренный из-за `pyinstaller` + `multiprocessing` (`freeze_support`). Оставить как есть.

---

## Порядок выполнения

```
1. BUG-1  — 5 мин,  1 строка
2. BUG-3  — 15 мин, 2 файла
3. BUG-2  — 20 мин, utils.py
4. BUG-4  — 30 мин, gui_server.py + utils.py
5. BUG-5  — 2 мин,  1 строка
6. REFACTOR-2 — 10 мин, удалить мёртвый код
7. REFACTOR-1 — 1-2 часа, серьёзный рефакторинг Upgrader
```
