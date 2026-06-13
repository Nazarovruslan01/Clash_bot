import sys
import time
import threading
import logging
from pathlib import Path
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, overload
if TYPE_CHECKING:
    from numpy.typing import NDArray
else:
    NDArray = Any
import configs
from configs import *

logger = logging.getLogger("coc_bot")

if sys.platform == "win32":
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

APP_DATA_DIR = Path.home() / ".CoC_Bot"
APP_DATA_DIR.mkdir(exist_ok=True)

if getattr(sys, "frozen", False):
    CACHE_PATH = APP_DATA_DIR / "cache.json"
else:
    CACHE_PATH = Path(__file__).parent / "cache.json"

INSTANCE_ID = None
GUI_SERVER_PORT = None
ADB_ADDRESS, ADB_DEVICE, MINITOUCH_DEVICE = None, None, None
ADB_WINDOW_DIMS = WINDOW_DIMS

def parse_args(debug=None, id=None, gui=None):
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", default=configs.DEBUG, help="Enable debug mode")
    parser.add_argument("--id", type=str, default=None, help="Instance ID")
    parser.add_argument("--gui", action="store_true", default=configs.LOCAL_GUI, help="Run with GUI")
    args = parser.parse_args()
    configs.DEBUG = args.debug if debug is None else debug
    configs.LOCAL_GUI = args.gui if gui is None else gui
    if id is not None:
        assert id in configs.INSTANCE_IDS, f"Invalid instance ID. Must be one of: {configs.INSTANCE_IDS}"
        args.id = id
    elif args.id is None and not configs.LOCAL_GUI:
        args.id = configs.DEFAULT_INSTANCE_ID
    return args

def init_instance(id):
    global INSTANCE_ID, ADB_ADDRESS
    import requests
    
    assert id in configs.INSTANCE_IDS, f"Invalid instance ID. Must be one of: {configs.INSTANCE_IDS}"
    INSTANCE_ID = id
    ADB_ADDRESS = configs.ADB_ADDRESSES[configs.INSTANCE_IDS.index(INSTANCE_ID)]
    if WEB_APP_URL != "":
        if "pythonanywhere.com" in WEB_APP_URL:
            Scheduler.add_job(extend_pythonanywhere_hosting, args=(configs.PA_USERNAME, configs.PA_PASSWORD), trigger="interval", hours=24)
        
        try:
            requests.post(
                f"{WEB_APP_URL}/instances",
                json={"id": INSTANCE_ID},
                timeout=(10, 20)
            )
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: logger.debug("init_instance: %s", e)

def _local_gui_port():
    from gui import get_gui
    gui = get_gui()
    return gui.server_port if gui is not None else GUI_SERVER_PORT

def disable_sleep():
    import sys, subprocess, ctypes, os, shutil
    
    if sys.platform == "darwin":
        sleep_helper_temp = Path(__file__).parent / "sleep_helper.sh"
        sleep_helper_permanent = APP_DATA_DIR / "sleep_helper.sh"
        shutil.copyfile(sleep_helper_temp, sleep_helper_permanent)
        os.chmod(sleep_helper_permanent, 0o755)
        cmd = f'do shell script "{sleep_helper_permanent} {os.getpid()}" with administrator privileges'
        subprocess.Popen(
            ["osascript", "-e", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    elif sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    Exit_Handler.register(enable_sleep)

def enable_sleep():
    import sys, ctypes
    
    if sys.platform == "darwin":
        pass
    elif sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

def has_gemini_api():
    """Check if Gemini API is configured and ready to use."""
    return bool(configs.GEMINI_API_KEY and configs.GEMINI_API_KEY.strip())

def safe_adb_shell(cmd, timeout=30):
    if ADB_DEVICE is None:
        raise RuntimeError("ADB_DEVICE is None")
    return ADB_DEVICE.shell(cmd, timeout=timeout)

def to_system_home():
    safe_adb_shell("input keyevent KEYCODE_HOME", timeout=30)

def connect_adb():
    global ADB_DEVICE, MINITOUCH_DEVICE, ADB_WINDOW_DIMS
    import subprocess, adbutils, os
    from pyminitouch import MNTDevice
    
    if ADB_ABS_DIR != "": os.environ["PATH"] = ADB_ABS_DIR + os.pathsep + os.environ["PATH"]
    subprocess.run(["adb", "start-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = adbutils.adb.connect(ADB_ADDRESS)
    if "connected" not in res:
        subprocess.run(["adb", "kill-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise Exception("Failed to connect to ADB.")
    device, mt_device = None, None
    try:
        device = adbutils.device(ADB_ADDRESS)
        mt_device = MNTDevice(ADB_ADDRESS)
        Exit_Handler.register(mt_device.stop)
    except (KeyboardInterrupt, SystemExit): raise
    except Exception:
        subprocess.run(["adb", "kill-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise Exception("Failed to get ADB device.")
    ADB_DEVICE, MINITOUCH_DEVICE = device, mt_device
    ADB_WINDOW_DIMS = ADB_DEVICE.window_size(landscape=False)

def running():
    import requests

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
            if configs.DEBUG: logger.debug("running: %s", e)
            return False
    port = _local_gui_port()
    if port is not None:
        try:
            response = requests.get(
                f"http://localhost:{port}/{INSTANCE_ID}/running",
                timeout=(1, 2)
            )
            if response.status_code == 200:
                return response.json().get("running", False)
            return False
        except Exception as e:
            if configs.DEBUG: logger.debug("running: %s", e)
            return False
    return True

def check_color(color, frame, tol=10):
    import numpy as np
    assert len(frame.shape) == 3 and frame.shape[2] == 3, "Frame must be a color image"
    diff = np.abs(frame - np.array(color).reshape((1, 1, 3))).sum(2) <= tol
    return np.any(diff)

def filter_color(color, frame, tol=10, return_mask=False):
    import numpy as np
    assert len(frame.shape) == 3 and frame.shape[2] == 3
    mask = np.abs(frame - np.array(color).reshape((1, 1, 3))).sum(2) <= tol
    frame_filtered = frame.copy()
    frame_filtered[~mask] = [0, 0, 0]
    if return_mask:
        return frame_filtered, mask
    return frame_filtered

def get_vocab():
    import json, time, portalocker
    from bs4 import BeautifulSoup
    from curl_cffi import requests as curl_requests
    
    other_words = [
        "prince",
        "copter",
    ]
    
    data = {}
    existing_vocab = None
    for _ in range(1):
        if CACHE_PATH.exists():
            with portalocker.Lock(CACHE_PATH, "r", timeout=5) as f:
                data = json.load(f)
                if "vocab" in data:
                    existing_vocab = set(data["vocab"]["text"] + other_words)
                    if time.time() - data["vocab"]["last_updated"] > 86400: break
                    return list(existing_vocab)
    
    vocab = set()
    endpoints = [
        "A-I",
        "J-P",
        "Q-Z",
    ]

    for endpoint in endpoints:
        # Bypass bot detection
        res = curl_requests.get(
            f"https://clashofclans.fandom.com/wiki/Glossary/{endpoint}",
            timeout=(10, 20),
            impersonate="chrome",
        )
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "lxml")
            elements = soup.select("h3 span.mw-headline")
            for e in elements:
                words = [s for s in e.text.lower().split(" ") if len(s) > 2]
                vocab = vocab.union(words)
        else:
            if existing_vocab is not None: return existing_vocab
            raise Exception("Failed to update vocabulary")
    
    vocab = vocab.union(other_words)
    text = sorted(list(vocab))
    data["vocab"] = {
        "last_updated": time.time(),
        "text": text,
    }
    
    with portalocker.Lock(CACHE_PATH, "w", timeout=5) as f:
        json.dump(data, f, indent=4)

    return list(vocab)

def spell_check(text, cutoff=70):
    import re
    from rapidfuzz import process, distance
    
    def spell_scorer(a, b, score_cutoff=0):
        lev = distance.Levenshtein.distance(a, b)
        length_penalty = abs(len(a) - len(b)) * 0.5
        score = 100 - 10 * (lev + length_penalty)
        return score if score >= score_cutoff else 0
    
    vocab = get_vocab()
    words = re.split(r"[ _]+", text)
    results = []

    for word in words:
        suggestion = word
        if word not in vocab:
            match = process.extractOne(word, vocab, scorer=spell_scorer, score_cutoff=cutoff)
            if match is not None: suggestion = match[0]
        results.append(suggestion)

    return " ".join(results)

def fix_digits(text):
    if type(text) is list:
        return [fix_digits(t) for t in text]
    return text.lower().replace('o', '0').replace('/', '1').replace('i', '1').replace('z', '2').replace('s', '5').replace('b', '6').replace('j', '7').replace('&', '8')

def parse_time(text):
    import re
    if type(text) is list:
        return [parse_time(t) for t in text]
    try:
        text = text.lower().replace(' ', '').replace('-', '')
        units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        pattern = re.compile(r"(\d+)([dhms])")
        seconds = sum(int(v) * units[u] for v, u in pattern.findall(text))
        return seconds
    except (KeyboardInterrupt, SystemExit): raise
    except Exception: return None

def to_int_array(*args):
    import numpy as np
    return np.array(list(map(int, args)))

@lru_cache(maxsize=128)
def _get_font(font_name, font_size):
    from PIL import ImageFont
    font_path = Asset_Manager.fonts.get(font_name)
    return ImageFont.truetype(font_path, font_size)

def render_text(text, font, font_size, color=(255, 255, 255)):
    import numpy as np
    from PIL import Image, ImageDraw

    pil_font = _get_font(font, font_size)
    temp = Image.new("RGB", (1, 1))
    bbox = ImageDraw.Draw(temp).textbbox((0, 0), text, font=pil_font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    render = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(render).text((-bbox[0], -bbox[1]), text, font=pil_font, fill=color)
    render = np.array(render)
    return render

def get_telegram_chat_id():
    import portalocker, requests, json
    
    data = {}
    if CACHE_PATH.exists():
        with portalocker.Lock(CACHE_PATH, "r", timeout=5) as f:
            data = json.load(f)
            if "telegram_chat_id" in data: return data["telegram_chat_id"]
    
    res = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
        timeout=(10, 20)
    )
    if res.status_code == 200:
        res = res.json()
        if res["ok"] and len(res["result"]) > 0:
            chat_id = res["result"][-1]["message"]["chat"]["id"]
            data["telegram_chat_id"] = chat_id
            with portalocker.Lock(CACHE_PATH, "w", timeout=5) as f:
                json.dump(data, f, indent=4)
            return chat_id

    raise Exception("Failed to get Telegram chat ID")

def send_notification(text):
    import requests

    payload = {"data": text, "time_stamp": time.time()}
    if WEB_APP_URL != "":
        try:
            requests.post(
                f"{WEB_APP_URL}/{INSTANCE_ID}/notify",
                json=payload,
                timeout=(1, 2)
            )
        except (KeyboardInterrupt, SystemExit): raise
        except Exception: pass
    port = _local_gui_port()
    if port is not None:
        try:
            requests.post(
                f"http://localhost:{port}/{INSTANCE_ID}/notify",
                json=payload,
                timeout=(1, 2)
            )
        except (KeyboardInterrupt, SystemExit): raise
        except Exception: pass

    if TELEGRAM_BOT_TOKEN != "":
        try:
            telegram_text = f"[{INSTANCE_ID}]\n{text}"
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": get_telegram_chat_id(),"text": telegram_text},
                timeout=(1, 2)
            )
        except (KeyboardInterrupt, SystemExit): raise
        except Exception: pass

def extend_pythonanywhere_hosting(username, password):
    import requests
    
    assert "pythonanywhere.com" in WEB_APP_URL
    base_url = "https://www.pythonanywhere.com"
    login_url = f"{base_url}/login/"
    webapps_url = f"{base_url}/user/{username}/webapps/"
    extend_url = f"{base_url}/user/{username}/webapps/{username}.pythonanywhere.com/extend"
    
    headers = {"Referer": base_url}

    session = requests.Session()
    
    # Login
    session.get(login_url)
    session.post(
        login_url,
        data={
            "csrfmiddlewaretoken": session.cookies.get_dict().get("csrftoken"),
            "auth-username": username,
            "auth-password": password,
            "login_view-current_step": "auth",
        },
        headers=headers,
    )
    assert "Log out" in session.get(base_url).text
    
    # Extend hosting
    session.get(webapps_url)
    res = session.post(
        extend_url,
        headers=headers,
        data={"csrfmiddlewaretoken": session.cookies.get_dict().get("csrftoken")},
    )
    assert res.url == webapps_url

def to_home_base():
    import cv2, time, numpy as np

    try:
        get_home_builders(1)
        return
    except (KeyboardInterrupt, SystemExit): raise
    except: pass

    Input_Handler.zoom(dir="out")
    for _ in range(3):
        Input_Handler.swipe_up(
            y1=0.5,
            y2=1.0,
        )
    for _ in range(3):
        Input_Handler.swipe_left(
            x1=1.0,
            x2=0.0,
        )

    scale_templates = []
    for scale in np.arange(0.43, 0.47, 0.01):
        template = cv2.resize(Asset_Manager.misc_assets["boat_icon"], None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        scale_templates.append(template)

    for _ in range(5):
        xys = Frame_Handler.batch_locate(scale_templates, grayscale=True, thresh=0.7, ref="cc")
        for x, y in xys:
            if x is None or y is None: continue
            Input_Handler.click(x, y, jitter=False)
            human_delay(2.0, spread=0.2)
            return
    raise Exception("Failed to navigate to home base")

def get_home_builders(timeout=60, return_amount=True, raise_exception=True, use_cached_frame=False):
    import time, cv2, re

    start = time.time()
    while True:
        try:
            section = Frame_Handler.get_frame_section(0.32, 0.01, 0.52, 0.08, grayscale=False, use_cached=use_cached_frame)
            if configs.DEBUG: Frame_Handler.save_frame(section, "debug/home_builders.png")

            raw = ''.join(OCR_Handler.get_text(section)).replace(' ', '')
            match = re.search(r'(\d+)[/|Il](\d+)', raw) or re.search(r'\d+', fix_digits(raw))
            if not match:
                if raise_exception: raise Exception("No builder count found")
                return 0 if return_amount else False

            available = int(fix_digits(match.group(1))) if match.lastindex else int(fix_digits(match.group()))
            return available if return_amount else True
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: logger.debug("get_home_builders: %s", e)
        human_delay(0.5, spread=0.1)
        if time.time() > start + timeout: break
    raise Exception("Failed to get home builders")

def start_coc(timeout=120):
    import time
    
    try:
        if not running(): return False
        to_system_home()
        logger.info("Starting CoC...")
        i = 0
        start = time.time()
        while time.time() - start < timeout:
            if not running(): return False
            safe_adb_shell(f"am start {'-S' if i==0 else ''} -W -n com.supercell.clashofclans/com.supercell.titan.GameApp", timeout=30)
            human_delay(25, spread=0.4)
            Frame_Handler.get_frame()

            try:
                get_home_builders(10, return_amount=False, use_cached_frame=True)
                break
            except (KeyboardInterrupt, SystemExit): raise
            except: pass

            try:
                get_builder_builders(10, return_amount=False, use_cached_frame=True)
                break
            except (KeyboardInterrupt, SystemExit): raise
            except: pass

            cont_x, cont_y = Frame_Handler.locate(Asset_Manager.misc_assets["continue"], grayscale=False, thresh=0.8, ref="cc", use_cached=True)
            if cont_x is not None and cont_y is not None:
                Input_Handler.click(cont_x, cont_y, jitter=False)

            i += 1
        if time.time() - start > timeout:
            stop_coc()
            update_coc()
            raise Exception("Failed to start CoC")
        logger.info("CoC started")
        return True
    except (KeyboardInterrupt, SystemExit): raise
    except:
        return False

def reset_devices():
    global ADB_DEVICE, MINITOUCH_DEVICE, ADB_WINDOW_DIMS
    ADB_DEVICE = None
    MINITOUCH_DEVICE = None
    ADB_WINDOW_DIMS = WINDOW_DIMS

def stop_coc():
    if ADB_DEVICE is None:
        if configs.DEBUG: logger.debug("stop_coc: ADB_DEVICE is None, skipping")
        return
    logger.info("Stopping CoC...")
    try:
        safe_adb_shell("am force-stop com.supercell.clashofclans", timeout=30)
    except (KeyboardInterrupt, SystemExit): raise
    except Exception as e:
        if configs.DEBUG: logger.debug("stop_coc force-stop failed: %s", e)
    try:
        to_system_home()
    except (KeyboardInterrupt, SystemExit): raise
    except Exception as e:
        if configs.DEBUG: logger.debug("stop_coc to_system_home failed: %s", e)
    logger.info("CoC stopped")

def update_coc(timeout=10):
    import uiautomator2 as u2
    safe_adb_shell('am start -a android.intent.action.VIEW -d "market://details?id=com.supercell.clashofclans"', timeout=30)
    try:
        u2.connect(ADB_ADDRESS)(text="Play").click(timeout=timeout)
        for _ in range(3): u2.connect(ADB_ADDRESS)(text="Play").click(timeout=0)
    except (KeyboardInterrupt, SystemExit): raise
    except: pass
    to_system_home()

def to_builder_base():
    import cv2, time, numpy as np

    try:
        get_builder_builders(1)
        return
    except (KeyboardInterrupt, SystemExit): raise
    except: pass

    for _ in range(3):
        Input_Handler.zoom(dir="in")
    for _ in range(2):
        Input_Handler.zoom(dir="out", percent=0.75)
    for _ in range(3):
        Input_Handler.swipe_right()
        Input_Handler.swipe_up()

    scale_templates = []
    for scale in np.arange(0.43, 0.47, 0.01):
        template = cv2.resize(Asset_Manager.misc_assets["boat_icon"], None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        scale_templates.append(template)

    for _ in range(5):
        xys = Frame_Handler.batch_locate(scale_templates, grayscale=True, thresh=0.7, ref="cc")
        for x, y in xys:
            if x is None or y is None: continue
            Input_Handler.click(x, y, jitter=False)
            human_delay(2.0, spread=0.2)
            return
        Input_Handler.swipe(x1=0.5, y1=0.5, x2=0.25, y2=0.75, hold_end_time=100)
    raise Exception("Failed to navigate to builder base")

def get_builder_builders(timeout=60, return_amount=True, raise_exception=True, use_cached_frame=False):
    import time, cv2, re

    start = time.time()
    while True:
        try:
            section = Frame_Handler.get_frame_section(0.05, 0.01, 0.55, 0.08, grayscale=False, use_cached=use_cached_frame)
            if configs.DEBUG: Frame_Handler.save_frame(section, "debug/builder_builders.png")

            raw = ''.join(OCR_Handler.get_text(section)).replace(' ', '')
            match = re.search(r'(\d+)[/|Il](\d+)', raw) or re.search(r'\d+', fix_digits(raw))
            if not match:
                if raise_exception: raise Exception("No builder count found")
                return 0 if return_amount else False

            available = int(fix_digits(match.group(1))) if match.lastindex else int(fix_digits(match.group()))
            return available if return_amount else True
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: logger.debug("get_builder_builders: %s", e)
        human_delay(0.5, spread=0.1)
        if time.time() > start + timeout: break
    raise Exception("Failed to get builder builders")

def human_delay(base, spread=0.3):
    """Sleep for base * uniform(1-spread, 1+spread) seconds.

    Args:
        base: Base delay in seconds.
        spread: Fractional variation. 0.3 means actual delay is base * [0.7, 1.3].
                Use 0.1 for short pauses (≤0.1s), 0.3 for medium, 0.4 for long.
    """
    import time
    Input_Handler._ensure_rng()
    actual = base * (1 + (2 * Input_Handler.rng.random() - 1) * spread)
    time.sleep(max(0, actual))

def require_exit(n=5, delay=0.1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = None
            try: result = func(*args, **kwargs)
            except (KeyboardInterrupt, SystemExit): raise
            except: pass
            Input_Handler.click_back(n, delay)
            return result
        return wrapper
    return decorator

class Exit_Handler:
    RUN_AT_EXIT = []

    @classmethod
    def register(cls, func):
        import atexit
        atexit.register(func)
        cls.RUN_AT_EXIT.append(func)
        return func

    @classmethod
    def unregister(cls, func):
        import atexit
        atexit.unregister(func)
        cls.RUN_AT_EXIT = [f for f in cls.RUN_AT_EXIT if f != func]

    @classmethod
    def handle_sig(cls, sig, frame):
        import signal
        for func in cls.RUN_AT_EXIT:
            try: func()
            except: pass
        if sig == signal.SIGINT:
            raise KeyboardInterrupt
        sys.exit(0)

    @classmethod
    def setup_signal_handlers(cls):
        import signal
        signals = [signal.SIGINT, signal.SIGTERM]
        if sys.platform != "win32":
            signals.append(signal.SIGHUP)
        for sig in signals:
            signal.signal(sig, cls.handle_sig)

Exit_Handler.setup_signal_handlers()

class Task_Handler:
    
    cached_exclusions = []
    
    @classmethod
    def get_exclusions(cls, use_cached=False):
        import requests

        if use_cached:
            return cls.cached_exclusions
        if WEB_APP_URL != "":
            res = requests.get(
                f"{WEB_APP_URL}/{INSTANCE_ID}/exclude",
                timeout=(10, 20)
            )
            if res.status_code == 200:
                cls.cached_exclusions = res.json().get("exclusions", [])
        elif configs.LOCAL_GUI:
            port = _local_gui_port()
            if port is not None:
                res = requests.get(
                    f"http://localhost:{port}/{INSTANCE_ID}/exclude",
                    timeout=(10, 20)
                )
                if res.status_code == 200:
                    cls.cached_exclusions = res.json().get("exclusions", [])
        return cls.cached_exclusions

    @classmethod
    def home_base_priority_excluded(cls, **kwargs):
        try:
            return "home_base_priority" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.PRIORITY_HOME_BASE_UPGRADES

    @classmethod
    def home_lab_priority_excluded(cls, **kwargs):
        try:
            return "home_lab_priority" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.PRIORITY_HOME_LAB_UPGRADES
    
    @classmethod
    def builder_base_priority_excluded(cls, **kwargs):
        try:
            return "builder_base_priority" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.PRIORITY_BUILDER_BASE_UPGRADES
    
    @classmethod
    def builder_lab_priority_excluded(cls, **kwargs):
        try:
            return "builder_lab_priority" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.PRIORITY_BUILDER_LAB_UPGRADES

    @classmethod
    def heroes_excluded(cls, **kwargs):
        try:
            return "heroes" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.UPGRADE_HEROES

    @classmethod
    def home_base_excluded(cls, **kwargs):
        try:
            return "home_base" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.UPGRADE_HOME_BASE

    @classmethod
    def builder_base_excluded(cls, **kwargs):
        try:
            return "builder_base" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.UPGRADE_BUILDER_BASE

    @classmethod
    def home_lab_excluded(cls, **kwargs):
        try:
            return "home_lab" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.UPGRADE_HOME_LAB

    @classmethod
    def builder_lab_excluded(cls, **kwargs):
        try:
            return "builder_lab" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.UPGRADE_BUILDER_LAB

    @classmethod
    def home_attacks_excluded(cls, **kwargs):
        try:
            return "home_attacks" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.ATTACK_HOME_BASE

    @classmethod
    def builder_attacks_excluded(cls, **kwargs):
        try:
            return "builder_attacks" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.ATTACK_BUILDER_BASE

    @classmethod
    def lab_assistant_excluded(cls, **kwargs):
        try:
            return "lab_assistant" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.ASSIGN_LAB_ASSISTANT

    @classmethod
    def builder_apprentice_excluded(cls, **kwargs):
        try:
            return "builder_apprentice" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except:
            return not configs.ASSIGN_BUILDER_ASSISTANT

    @classmethod
    def magic_items_excluded(cls, **kwargs):
        try:
            return "magic_items" in cls.get_exclusions(**kwargs)
        except (KeyboardInterrupt, SystemExit): raise
        except Exception:
            return not (configs.USE_BUILDER_POTION or configs.USE_RESEARCH_POTION or configs.USE_TRAINING_POTION)

class OCR_Handler:

    backoff_time = 0
    _model = None

    @classmethod
    def get_text(cls, frame):
        import time
        if configs.GEMINI_API_KEY != "":
            if time.time() > cls.backoff_time:
                try: return cls.external_ocr(frame)
                except (KeyboardInterrupt, SystemExit): raise
                except: cls.backoff_time = time.time() + 600
        return cls.local_ocr(frame)

    @classmethod
    def local_ocr(cls, frame):
        if not hasattr(cls, 'reader'):
            import easyocr
            cls.reader = easyocr.Reader(['en'], gpu=True)
        result = cls.reader.readtext(frame)
        return [text for _, text, _ in result if text.strip()]

    @classmethod
    def external_ocr(cls, frame):
        import cv2
        import PIL.Image
        from google import genai
        from google.genai import types

        if cls._model is None:
            cls._model = genai.Client(api_key=configs.GEMINI_API_KEY)

        img = PIL.Image.fromarray(frame)
        response = cls._model.models.generate_content(
            model=configs.GEMINI_MODEL,
            contents=["what text is in this image? respond ONLY with the text. if there is no text respond with ~", img],
            config=types.GenerateContentConfig(
                max_output_tokens=32,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return (response.text or '').replace('~', '').splitlines()

    @classmethod
    def gemini_game_state(cls, frame) -> str:
        """Fallback game state recognition using Gemini vision."""
        import time
        import json
        import PIL.Image
        from google import genai
        from google.genai import types

        if cls._model is None:
            cls._model = genai.Client(api_key=configs.GEMINI_API_KEY)

        try:
            img = PIL.Image.fromarray(frame)
            response = cls._model.models.generate_content(
                model=configs.GEMINI_MODEL,
                contents=["What screen is this in Clash of Clans? Reply with only one word from this list: home, builder, attack, loading, dialog, unknown", img],
                config=types.GenerateContentConfig(
                    max_output_tokens=8,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            state = (response.text or "unknown").strip().lower()
            valid_states = ("home", "builder", "attack", "loading", "dialog", "unknown")
            return state if state in valid_states else "unknown"
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            return "unknown"

    @classmethod
    def gemini_find_button(cls, frame, description: str) -> tuple:
        """Find a button in the screenshot by description using Gemini vision."""
        import json
        import PIL.Image
        from google import genai
        from google.genai import types

        if cls._model is None:
            cls._model = genai.Client(api_key=configs.GEMINI_API_KEY)

        try:
            img = PIL.Image.fromarray(frame)
            response = cls._model.models.generate_content(
                model=configs.GEMINI_MODEL,
                contents=[f'Find the "{description}" in this Clash of Clans screenshot. Return ONLY valid JSON with normalized coordinates: {{"x": 0.0-1.0 or null, "y": 0.0-1.0 or null}}', img],
                config=types.GenerateContentConfig(
                    max_output_tokens=32,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            data = json.loads(response.text or "{}")
            x = data.get("x")
            y = data.get("y")
            return (x, y) if (isinstance(x, (int, float)) and isinstance(y, (int, float))) else (None, None)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            return (None, None)

    @classmethod
    def gemini_analyze_base(cls, frame) -> dict | None:
        """Analyze enemy base layout for optimal attack strategy."""
        import json
        import PIL.Image
        from google import genai
        from google.genai import types

        if cls._model is None:
            cls._model = genai.Client(api_key=configs.GEMINI_API_KEY)

        try:
            img = PIL.Image.fromarray(frame)
            prompt = """Analyze this Clash of Clans enemy base screenshot. Return ONLY valid JSON:
{
  "town_hall": [x_normalized, y_normalized],
  "resource_cluster": [x_normalized, y_normalized],
  "recommended_deploy_x": x_normalized,
  "recommended_deploy_y": y_normalized,
  "base_type": "dead|active|engineered",
  "notes": "brief observation"
}
All coordinates normalized to 0.0-1.0. Null values for missing elements."""
            
            response = cls._model.models.generate_content(
                model=configs.GEMINI_MODEL,
                contents=[prompt, img],
                config=types.GenerateContentConfig(
                    max_output_tokens=128,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            data = json.loads(response.text or "{}")
            return data if "recommended_deploy_x" in data else None
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            return None

    @classmethod
    def gemini_evaluate_match(cls, frame) -> dict | None:
        """Evaluate loot value and skip status for current match."""
        import json
        import PIL.Image
        from google import genai
        from google.genai import types

        if cls._model is None:
            cls._model = genai.Client(api_key=configs.GEMINI_API_KEY)

        try:
            img = PIL.Image.fromarray(frame)
            prompt = """Read the loot amounts in this Clash of Clans matchmaking screen. Return ONLY valid JSON:
{
  "gold": amount_or_null,
  "elixir": amount_or_null,
  "dark_elixir": amount_or_null,
  "skip": true_if_low_value
}"""
            
            response = cls._model.models.generate_content(
                model=configs.GEMINI_MODEL,
                contents=[prompt, img],
                config=types.GenerateContentConfig(
                    max_output_tokens=64,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            data = json.loads(response.text or "{}")
            # Validate response has at least one loot value to avoid false negatives on API errors
            if isinstance(data, dict) and any(k in data for k in ("gold", "elixir", "dark_elixir")):
                return data
            return None
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            return None

class Asset_Manager:
    fonts = {}
    misc_assets = {}
    upgrader_assets = {}
    attacker_assets = {}
    magic_items_assets = {}
    
    @staticmethod
    def resource_path(rel_path):
        import sys
        from pathlib import Path
        if hasattr(sys, "_MEIPASS"):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent.parent.resolve()
        return base_path / rel_path
    
    @classmethod
    def load_fonts(cls):
        import os
        cls.fonts = {}
        path = cls.resource_path("assets/fonts")
        for file in os.listdir(path):
            cls.fonts[file.replace('.ttf', '')] = str(path / file)

    @classmethod
    def load_misc_assets(cls):
        import os, cv2
        assets = {}
        path = cls.resource_path("assets/misc")
        for file in os.listdir(path):
            if not file.endswith('.png'): continue
            img = cv2.imread(str(path / file), cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"Asset not found: {path / file}")
            assets[file.replace('.png', '')] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        cls.misc_assets = assets
    
    @classmethod
    def load_upgrader_assets(cls):
        import os, cv2
        assets = {}
        path = cls.resource_path("assets/upgrader")
        for file in os.listdir(path):
            if not file.endswith('.png'): continue
            img = cv2.imread(str(path / file), cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"Asset not found: {path / file}")
            assets[file.replace('.png', '')] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        cls.upgrader_assets = assets

    @classmethod
    def load_attacker_assets(cls):
        import os, cv2
        assets = {}
        path = cls.resource_path("assets/attacker")
        for file in os.listdir(path):
            if not file.endswith('.png'): continue
            img = cv2.imread(str(path / file), cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"Asset not found: {path / file}")
            assets[file.replace('.png', '')] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        cls.attacker_assets = assets

    @classmethod
    def load_magic_items_assets(cls):
        import os, cv2
        assets = {}
        path = cls.resource_path("assets/magic_items")
        if not path.exists(): cls.magic_items_assets = assets; return
        for file in os.listdir(path):
            if not file.endswith('.png'): continue
            img = cv2.imread(str(path / file), cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"Asset not found: {path / file}")
            assets[file.replace('.png', '')] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        cls.magic_items_assets = assets

Asset_Manager.load_misc_assets()
Asset_Manager.load_upgrader_assets()
Asset_Manager.load_attacker_assets()
Asset_Manager.load_magic_items_assets()
Asset_Manager.load_fonts()

class Input_Handler:
    rng = None  # initialized by init_rng() at startup

    @classmethod
    def init_rng(cls, seed=None):
        """Initialize the session RNG. Seed=None uses current time, int for reproducibility."""
        import numpy as np, time
        if seed is not None:
            cls.rng = np.random.default_rng(seed)
        else:
            cls.rng = np.random.default_rng(int(time.time()))

    @classmethod
    def _ensure_rng(cls):
        """Lazily initialize rng if not yet set."""
        if cls.rng is None:
            cls.init_rng()

    PRESSURE_RANGE = (80, 120)

    @classmethod
    def _random_pressure(cls):
        """Generate a random touch pressure within PRESSURE_RANGE."""
        cls._ensure_rng()
        return int(cls.rng.integers(cls.PRESSURE_RANGE[0], cls.PRESSURE_RANGE[1]))

    @classmethod
    def _jitter(cls, x, y, sigma=0.008):
        """Apply Gaussian noise to coordinates, clamped away from screen edges."""
        cls._ensure_rng()
        x = max(0.02, min(0.98, x + cls.rng.normal(0, sigma)))
        y = max(0.02, min(0.98, y + cls.rng.normal(0, sigma)))
        return x, y

    @classmethod
    def down(cls, x, y, pointer=0, jitter=True):
        if MINITOUCH_DEVICE is None: raise RuntimeError("MINITOUCH_DEVICE is None")
        from pyminitouch import CommandBuilder
        if jitter:
            x, y = cls._jitter(x, y)
        if x < 0: x = 1 + x
        if y < 0: y = 1 + y
        MAX_X = int(MINITOUCH_DEVICE.connection.max_x)
        MAX_Y = int(MINITOUCH_DEVICE.connection.max_y)
        x = int(x * MAX_X)
        y = int(y * MAX_Y)
        builder = CommandBuilder()
        builder.down(pointer, x, y, cls._random_pressure())
        builder.publish(MINITOUCH_DEVICE.connection)

    @classmethod
    def up(cls, pointer=0):
        if MINITOUCH_DEVICE is None: raise RuntimeError("MINITOUCH_DEVICE is None")
        from pyminitouch import CommandBuilder
        builder = CommandBuilder()
        builder.up(pointer)
        builder.publish(MINITOUCH_DEVICE.connection)

    @classmethod
    def click(cls, x, y, n=1, delay=0, pointer=0, jitter=True):
        if MINITOUCH_DEVICE is None: raise RuntimeError("MINITOUCH_DEVICE is None")
        import time
        from pyminitouch import CommandBuilder
        if jitter:
            x, y = cls._jitter(x, y)
        if x < 0: x = 1 + x
        if y < 0: y = 1 + y
        MAX_X = int(MINITOUCH_DEVICE.connection.max_x)
        MAX_Y = int(MINITOUCH_DEVICE.connection.max_y)
        x = int(x * MAX_X)
        y = int(y * MAX_Y)
        pressure = cls._random_pressure()
        builder = CommandBuilder()
        for _ in range(n):
            builder.down(pointer, x, y, pressure)
            builder.commit()
            builder.up(pointer)
            builder.publish(MINITOUCH_DEVICE.connection)
            time.sleep(delay)

    @classmethod
    def click_exit(cls, n=1, delay=0):
        cls.click(0.02, 0.02, n, delay=delay, jitter=False)

    @classmethod
    def click_back(cls, n=1, delay=0):
        import time
        for _ in range(n):
            safe_adb_shell("input keyevent 4", timeout=5)
            time.sleep(delay)

    @classmethod
    def multi_click(cls, x1, y1, x2, y2, duration=0):
        if MINITOUCH_DEVICE is None: raise RuntimeError("MINITOUCH_DEVICE is None")
        x1, y1 = cls._jitter(x1, y1)
        x2, y2 = cls._jitter(x2, y2)
        MAX_X = int(MINITOUCH_DEVICE.connection.max_x)
        MAX_Y = int(MINITOUCH_DEVICE.connection.max_y)
        MINITOUCH_DEVICE.tap([(x1*MAX_X, y1*MAX_Y), (x2*MAX_X, y2*MAX_Y)], duration=duration)

    @classmethod
    def swipe(cls, x1, y1, x2, y2, duration=100, hold_end_time=0, inter_points=0, pointer=0, jitter=True):
        if MINITOUCH_DEVICE is None: raise RuntimeError("MINITOUCH_DEVICE is None")
        import time, numpy as np
        from pyminitouch import CommandBuilder

        if jitter:
            x1, y1 = cls._jitter(x1, y1)
            x2, y2 = cls._jitter(x2, y2)

        if x1 < 0: x1 = 1 + x1
        if y1 < 0: y1 = 1 + y1
        if x2 < 0: x2 = 1 + x2
        if y2 < 0: y2 = 1 + y2

        builder = CommandBuilder()

        MAX_X = int(MINITOUCH_DEVICE.connection.max_x)
        MAX_Y = int(MINITOUCH_DEVICE.connection.max_y)

        px1 = int(x1 * MAX_X)
        py1 = int(y1 * MAX_Y)
        px2 = int(x2 * MAX_X)
        py2 = int(y2 * MAX_Y)

        # Generate cubic Bezier curve with random control points
        # Perpendicular deviation scaled to screen size, not swipe distance,
        # to avoid large horizontal wobble on long vertical scrolls
        dx, dy = px2 - px1, py2 - py1
        dist = max(1, (dx*dx + dy*dy) ** 0.5)
        perp_x, perp_y = -dy / dist, dx / dist
        max_perp = max(MAX_X, MAX_Y) * 0.03  # cap at 3% of screen size

        cls._ensure_rng()
        magnitude1 = min(cls.rng.uniform(0.05, 0.15) * dist, max_perp)
        magnitude2 = min(cls.rng.uniform(0.05, 0.15) * dist, max_perp)
        sign1, sign2 = cls.rng.choice([-1, 1], size=2)

        cp1_x = int(px1 + dx/3 + perp_x * magnitude1 * sign1)
        cp1_y = int(py1 + dy/3 + perp_y * magnitude1 * sign1)
        cp2_x = int(px2 - dx/3 + perp_x * magnitude2 * sign2)
        cp2_y = int(py2 - dy/3 + perp_y * magnitude2 * sign2)

        # Bezier interpolation
        t_vals = np.linspace(0, 1, inter_points + 2)
        x_points = ((1-t_vals)**3 * px1 + 3*(1-t_vals)**2*t_vals * cp1_x +
                     3*(1-t_vals)*t_vals**2 * cp2_x + t_vals**3 * px2).astype(int)
        y_points = ((1-t_vals)**3 * py1 + 3*(1-t_vals)**2*t_vals * cp1_y +
                     3*(1-t_vals)*t_vals**2 * cp2_y + t_vals**3 * py2).astype(int)

        # Ease-in/out timing with ±10% random duration variation
        total_duration = duration * (1 + cls.rng.uniform(-0.1, 0.1))
        pressure = cls._random_pressure()

        def ease(t):
            return 3 * t * t - 2 * t * t * t

        builder.down(pointer, px1, py1, pressure=pressure)
        builder.publish(MINITOUCH_DEVICE.connection)
        # Skip first point (t=0) — it's identical to the down position
        for i, (x, y) in enumerate(zip(x_points[1:], y_points[1:]), start=1):
            builder.move(pointer, x, y, pressure=pressure)
            builder.publish(MINITOUCH_DEVICE.connection)
            if i < len(x_points) - 1:
                t = (i + 1) / (len(x_points) - 1)
                t_prev = i / (len(x_points) - 1)
                dt = total_duration * (ease(t) - ease(t_prev))
                if dt > 0: time.sleep(dt / 1000)
        if hold_end_time > 0: time.sleep(hold_end_time / 1000)
        builder.up(pointer)
        builder.publish(MINITOUCH_DEVICE.connection)

    @classmethod
    def swipe_up(cls, y1=0.5, y2=0.0, x=1.0, **kwargs):
        cls.swipe(x, y1, x, y2, **kwargs)

    @classmethod
    def swipe_down(cls, y1=0.5, y2=1.0, x=1.0, **kwargs):
        cls.swipe(x, y1, x, y2, **kwargs)

    @classmethod
    def swipe_left(cls, x1=0.5, x2=0.0, y=1.0, **kwargs):
        cls.swipe(x1, y, x2, y, **kwargs)

    @classmethod
    def swipe_right(cls, x1=0.5, x2=1.0, y=1.0, **kwargs):
        cls.swipe(x1, y, x2, y, **kwargs)

    @classmethod
    def zoom(cls, dir="out", percent=1.0):
        if MINITOUCH_DEVICE is None: raise RuntimeError("MINITOUCH_DEVICE is None")
        from pyminitouch import CommandBuilder

        builder = CommandBuilder()

        MAX_X = int(MINITOUCH_DEVICE.connection.max_x)
        MAX_Y = int(MINITOUCH_DEVICE.connection.max_y)

        # Jitter zoom x-coordinates, share y across both fingers for horizontal pinch
        cls._ensure_rng()
        left_in_x, _ = cls._jitter((0.15 + 0.30*percent), 0.5)
        left_out_x, _ = cls._jitter(0.15, 0.5)
        right_in_x, _ = cls._jitter((0.85 - 0.30*percent), 0.5)
        right_out_x, _ = cls._jitter(0.85, 0.5)
        y_shared = max(0.02, min(0.98, 0.5 + cls.rng.normal(0, 0.008)))

        left_in = to_int_array(left_in_x * MAX_X, y_shared * MAX_Y)
        left_out = to_int_array(left_out_x * MAX_X, y_shared * MAX_Y)
        right_in = to_int_array(right_in_x * MAX_X, y_shared * MAX_Y)
        right_out = to_int_array(right_out_x * MAX_X, y_shared * MAX_Y)

        start = [left_in, right_in] if dir=="in" else [left_out, right_out]
        end = [left_out, right_out] if dir=="in" else [left_in, right_in]

        pressure0 = cls._random_pressure()
        pressure1 = cls._random_pressure()

        builder.down(0, *start[0], pressure=pressure0)
        builder.down(1, *start[1], pressure=pressure1)
        builder.publish(MINITOUCH_DEVICE.connection)
        builder.move(0, *end[0], pressure=pressure0)
        builder.move(1, *end[1], pressure=pressure1)
        builder.commit()
        builder.publish(MINITOUCH_DEVICE.connection)
        builder.up(0)
        builder.up(1)
        builder.publish(MINITOUCH_DEVICE.connection)

    @classmethod
    def health_check(cls):
        """Verify minitouch is responsive with a no-op touch at screen corner."""
        try:
            cls.down(0.01, 0.01, pointer=0, jitter=False)
            cls.up(pointer=0)
            return True
        except Exception:
            return False

    @classmethod
    def idle_gesture(cls):
        """With ~30% probability, perform a short slow swipe (idle behavior)."""
        cls._ensure_rng()
        if cls.rng.random() > 0.3:
            return
        dist = cls.rng.uniform(0.02, 0.05)
        direction = cls.rng.choice(["up", "down", "left", "right"])
        duration = int(cls.rng.uniform(200, 400))
        center_x = cls.rng.uniform(0.3, 0.7)
        center_y = cls.rng.uniform(0.3, 0.7)
        if direction == "up":
            cls.swipe(center_x, center_y, center_x, center_y - dist, duration=duration, inter_points=3, jitter=False)
        elif direction == "down":
            cls.swipe(center_x, center_y, center_x, center_y + dist, duration=duration, inter_points=3, jitter=False)
        elif direction == "left":
            cls.swipe(center_x, center_y, center_x - dist, center_y, duration=duration, inter_points=3, jitter=False)
        else:
            cls.swipe(center_x, center_y, center_x + dist, center_y, duration=duration, inter_points=3, jitter=False)

class Frame_Handler:
    pool = None
    cached_frame = None
    _frame_lock = threading.Lock()
    
    @classmethod
    def grayscale(cls, frame):
        import cv2
        if len(frame.shape) == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        return frame
    
    @classmethod
    def high_contrast(cls, frame, thresh=200):
        frame = cls.grayscale(frame)
        frame[frame < thresh] = 0
        return frame
    
    @classmethod
    def crop(cls, frame, x1, y1, x2, y2):
        if x1 < 0: x1 = 1 + x1
        if y1 < 0: y1 = 1 + y1
        if x2 < 0: x2 = 1 + x2
        if y2 < 0: y2 = 1 + y2
        h, w = frame.shape[:2]
        return frame[int(h*y1):int(h*y2), int(w*x1):int(w*x2)]
    
    @classmethod
    def get_frame(cls, grayscale=True, high_contrast=False, thresh=200, use_cached=False):
        import cv2, numpy as np
        if use_cached and cls.cached_frame is not None:
            with cls._frame_lock:
                frame = cls.cached_frame.copy()
        else:
            if ADB_DEVICE is None: raise RuntimeError("ADB_DEVICE is None")
            frame = np.array(ADB_DEVICE.screenshot())
            frame = cv2.resize(frame, ADB_WINDOW_DIMS, interpolation=cv2.INTER_NEAREST)
            with cls._frame_lock:
                cls.cached_frame = frame.copy()
        if configs.DEBUG: cls.save_frame(frame, "debug/frame.png")
        if high_contrast: frame = cls.high_contrast(frame, thresh)
        elif grayscale: frame = cls.grayscale(frame)
        return frame

    @classmethod
    def get_frame_section(cls, x1, y1, x2, y2, high_contrast=False, thresh=200, grayscale=True, use_cached=False):
        frame = cls.get_frame(grayscale=grayscale, high_contrast=high_contrast, thresh=thresh, use_cached=use_cached)
        frame = cls.crop(frame, x1, y1, x2, y2)
        return frame

    @classmethod
    def save_frame(cls, frame, filename="frame.png"):
        import cv2
        if len(frame.shape) == 2:  # grayscale
            cv2.imwrite(filename, frame)
        else:
            cv2.imwrite(filename, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

    @classmethod
    def screenshot(cls, filename="debug/screenshot.png", grayscale=False):
        frame = cls.get_frame(grayscale=grayscale)
        cls.save_frame(frame, filename)
    
    @classmethod
    @overload
    def locate(cls, template: NDArray, frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = False, return_all: bool = True, use_cached: bool = False) -> list[tuple[float, float]]: ...
    @classmethod
    @overload
    def locate(cls, template: NDArray, frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = True, return_all: bool = True, use_cached: bool = False) -> list[tuple[float, float, float]]: ...
    @classmethod
    @overload
    def locate(cls, template: NDArray, frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = True, return_all: bool = False, use_cached: bool = False) -> tuple[float | None, float | None, float]: ...
    @classmethod
    @overload
    def locate(cls, template: NDArray, frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = False, return_all: bool = False, use_cached: bool = False) -> tuple[float | None, float | None]: ...
    @classmethod
    def locate(cls, template: NDArray, frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = False, return_all: bool = False, use_cached: bool = False):
        import cv2, numpy as np
        
        if grayscale: template = cls.grayscale(template)
        h, w = template.shape[:2]
        frame = cls.get_frame(grayscale=grayscale, use_cached=use_cached) if frame is None else frame
        fh, fw = frame.shape[:2]
        
        if h > fh or w > fw:
            if return_all:
                return []
            if return_confidence:
                return null_val, null_val, 0
            return null_val, null_val

        res = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if configs.DEBUG: logger.debug("max_val: %s", max_val)
        
        if return_all:
            ys, xs = np.where(res >= thresh)
            results = []
            for (x_loc, y_loc, val) in zip(xs, ys, res[ys, xs]):
                if ref[0] == 'c':
                    x_loc += w / 2
                elif ref[0] == 'r':
                    x_loc += w
                if ref[1] == 'c':
                    y_loc += h / 2
                elif ref[1] == 'b':
                    y_loc += h

                if return_confidence:
                    results.append((x_loc / fw, y_loc / fh, float(val)))
                else:
                    results.append((x_loc / fw, y_loc / fh))

            results.sort(key=lambda r: r[-1] if return_confidence else 0, reverse=True)
            return results
        
        if max_val > thresh:
            x_loc, y_loc = max_loc
            if ref[0] == 'c': x_loc += w / 2
            elif ref[0] == 'r': x_loc += w
            if ref[1] == 'c': y_loc += h / 2
            elif ref[1] == 'b': y_loc += h
            if return_confidence:
                return x_loc / fw, y_loc / fh, max_val
            else:
                return x_loc / fw, y_loc / fh
        if return_confidence:
            return null_val, null_val, max_val
        return null_val, null_val

    @classmethod
    @overload
    def batch_locate(cls, templates: list[NDArray], frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = False, return_all: bool = True, use_cached: bool = False) -> list[list[tuple[float, float]]]: ...
    @classmethod
    @overload
    def batch_locate(cls, templates: list[NDArray], frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = True, return_all: bool = True, use_cached: bool = False) -> list[list[tuple[float, float, float]]]: ...
    @classmethod
    @overload
    def batch_locate(cls, templates: list[NDArray], frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = True, return_all: bool = False, use_cached: bool = False) -> list[tuple[float | None, float | None, float]]: ...
    @classmethod
    @overload
    def batch_locate(cls, templates: list[NDArray], frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = False, return_all: bool = False, use_cached: bool = False) -> list[tuple[float | None, float | None]]: ...
    @classmethod
    def batch_locate(cls, templates: list[NDArray], frame: NDArray | None = None, grayscale: bool = True, thresh: float = 0.0, ref: Literal["cc", "lc", "rc", "cb", "rb", "lb", "cr", "lr", "rr", "br"] = "cc", null_val: int | None = None, return_confidence: bool = False, return_all: bool = False, use_cached: bool = False):
        from concurrent.futures import ThreadPoolExecutor
        
        if cls.pool is None:
            cls.pool = ThreadPoolExecutor()
            Exit_Handler.register(cls.pool.shutdown)
        
        frame = cls.get_frame(grayscale=grayscale, use_cached=use_cached) if frame is None else frame
        
        threads = []
        for template in templates:
            threads.append(cls.pool.submit(cls.locate, template, frame, grayscale, thresh, ref, null_val, return_confidence, return_all))
        return [thread.result() for thread in threads]

class Scheduler:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    @staticmethod
    def _shutdown_scheduler():
        try:
            Scheduler.scheduler.shutdown()
        except Exception:
            pass
    Exit_Handler.register(_shutdown_scheduler)
    
    add_job = scheduler.add_job

class Dev_Tools:
    @classmethod
    def optimal_template_font_size(cls, frame, text, font, font_size_range=(1, 100), color=(255, 255, 255), return_results=False, plot_results=False):
        import numpy as np, matplotlib.pyplot as plt
        templates = [render_text(text, font, size, color) for size in range(font_size_range[0], font_size_range[1] + 1)]
        results = Frame_Handler.batch_locate(templates, frame=frame, grayscale=True, return_confidence=True)
        confidences = [res[2] for res in results]
        optimal_size = confidences.index(max(confidences)) + font_size_range[0]
        
        if plot_results:
            plt.plot(np.arange(font_size_range[0], font_size_range[1] + 1), confidences)
            plt.xlabel("Font Size")
            plt.ylabel("Confidence")
            plt.title(f"Optimal Font Size: {optimal_size}")
            plt.show()
        
        if return_results:
            return optimal_size, results
        return optimal_size
