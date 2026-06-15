import logging
import utils
from utils import *
import configs
from upgrader import Upgrader
from attacker import Attacker

logger = logging.getLogger("coc_bot")

class CoC_Bot:
    def __init__(self):
        self.start_bluestacks()
        self.connect_adb()
        Input_Handler.init_rng(configs.SESSION_SEED)
        self.upgrader = Upgrader()
        self.attacker = Attacker()

    # ============================================================
    # 🖥️ System & Emulator Management
    # ============================================================
    
    def update_status(self, status):
        import requests

        if WEB_APP_URL != "":
            try:
                requests.post(
                    f"{WEB_APP_URL}/{utils.INSTANCE_ID}/status",
                    json={"status": status},
                    timeout=(1, 2)
                )
            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                if configs.DEBUG: logger.debug("update_status: %s", e)

        gui_port = utils._local_gui_port()
        if gui_port is not None:
            try:
                requests.post(
                    f"http://localhost:{gui_port}/{utils.INSTANCE_ID}/status",
                    json={"status": status},
                    timeout=(1, 2)
                )
            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                if configs.DEBUG: logger.debug("update_status: %s", e)
    
    def start_bluestacks(self):
        import sys, subprocess, time
        
        if sys.platform == "darwin":
            subprocess.Popen([
                "osascript", "-e",
                'tell application "BlueStacks" to launch\n'
                'tell application "BlueStacks" to set visible of front window to false'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 6
            subprocess.Popen([configs.BLUESTACKS_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
        
        for _ in range(120):
            if self.check_bluestacks():
                if configs.DEBUG: logger.debug("BlueStacks started")
                return
            human_delay(0.5, spread=0.1)
        
        raise Exception("BlueStacks failed to start.")
    
    def check_bluestacks(self):
        import psutil
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and 'bluestacks' in proc.info['name'].lower():
                return True
        return False

    def _recover(self):
        mt_device = utils.MINITOUCH_DEVICE
        if mt_device is not None:
            utils.Exit_Handler.unregister(mt_device.stop)
            try:
                mt_device.stop()
            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                if configs.DEBUG: logger.debug("_recover: minitouch stop failed: %s", e)
        utils.reset_devices()

        if not self.check_bluestacks():
            logger.warning("BlueStacks not running, restarting...")
            self.start_bluestacks()
        self.connect_adb()

        if utils.ADB_WINDOW_DIMS != configs.WINDOW_DIMS:
            logger.warning("ADB dimensions %s differ from config %s", utils.ADB_WINDOW_DIMS, configs.WINDOW_DIMS)

        # Verify minitouch is responsive
        if not Input_Handler.health_check():
            logger.warning("Minitouch health check failed, retrying connection...")
            self.connect_adb()
            if not Input_Handler.health_check():
                raise Exception("Minitouch unresponsive after recovery")

    def _validate_game_state(self):
        """Determine current game state: 'home', 'builder', 'loading', or 'unknown'."""
        try:
            if get_home_builders(1, return_amount=False, raise_exception=False) is not False:
                return "home"
        except Exception:
            pass
        try:
            if get_builder_builders(1, return_amount=False, raise_exception=False) is not False:
                return "builder"
        except Exception:
            pass
        # Check for "continue" button (game loading/reconnect)
        try:
            cont_x, cont_y = Frame_Handler.locate(
                Asset_Manager.misc_assets["continue"], grayscale=False, thresh=0.8, ref="cc", use_cached=True
            )
            if cont_x is not None and cont_y is not None:
                Input_Handler.click(cont_x, cont_y, jitter=False)
                return "loading"
        except Exception:
            pass

        # Fallback to Gemini vision for unknown screens with retry logic
        if configs.USE_AI_GAME_STATE and configs.GEMINI_API_KEY != "":
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    frame = Frame_Handler.get_frame(grayscale=False)
                    state = OCR_Handler.gemini_game_state(frame)
                    if state in ("home", "builder", "loading"):
                        logger.info("[Bot] Gemini recognized game state: %s", state)
                        return state
                    elif state in ("dialog", "attack"):
                        # Popup or attack screen detected, try to dismiss/exit
                        logger.debug("[Bot] Detected popup/dialog state, attempting to dismiss (attempt %d/%d)", attempt+1, max_retries)
                        Input_Handler.click_back()
                        human_delay(0.5)
                        # Continue to next iteration to re-check
                        continue
                    else:
                        return "unknown"
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:
                    pass

        return "unknown"

    def dismiss_popups(self, max_attempts=5):
        """Auto-dismiss popups like season pass or event notifications."""
        if not configs.USE_AI_POPUP_DISMISS or configs.GEMINI_API_KEY == "":
            return

        for attempt in range(max_attempts):
            try:
                frame = Frame_Handler.get_frame(grayscale=False)
                x, y = OCR_Handler.gemini_find_button(frame, "close or dismiss button")
                if x is None or y is None:
                    break
                Input_Handler.click(x, y, jitter=False)
                human_delay(0.5)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:
                break

    def connect_adb(self):
        import time
        for _ in range(120):
            try:
                connect_adb()
                if configs.DEBUG: logger.debug("Connected to ADB")
                return
            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                if configs.DEBUG: logger.debug("connect_adb: %s", e)
            human_delay(0.5, spread=0.1)
        raise Exception("Failed to connect to ADB.")
    
    # ============================================================
    # ⏱️ Task Execution
    # ============================================================
    
    def run(self):
        import time

        _err_count = 0

        while True:
            try:
                if not running():
                    _err_count = 0
                    human_delay(1.0)
                    continue

                if start_coc():
                    self.update_status("now")
                    self.dismiss_popups()

                    Task_Handler.get_exclusions()
                    exclude_home_base = Task_Handler.home_base_excluded(use_cached=True)
                    exclude_home_lab = Task_Handler.home_lab_excluded(use_cached=True)
                    skip_home_base_upgrades = exclude_home_base and exclude_home_lab
                    exclude_home_attacks = Task_Handler.home_attacks_excluded(use_cached=True)

                    exclude_builder_base = Task_Handler.builder_base_excluded(use_cached=True)
                    exclude_builder_lab = Task_Handler.builder_lab_excluded(use_cached=True)
                    skip_builder_base_upgrades = exclude_builder_base and exclude_builder_lab
                    exclude_builder_attacks = Task_Handler.builder_attacks_excluded(use_cached=True)

                    logger.info("=" * 44)
                    logger.info("Run started")
                    logger.info("  Home:    upgrades=%s  attacks=%s", 'on ' if not skip_home_base_upgrades else 'off', 'on ' if not exclude_home_attacks else 'off')
                    logger.info("  Builder: upgrades=%s  attacks=%s", 'on ' if not skip_builder_base_upgrades else 'off', 'on ' if not exclude_builder_attacks else 'off')

                    # Collect min_completion_time from upgrades
                    min_completion_time = None

                    # Check home base
                    if not skip_home_base_upgrades or not exclude_home_attacks:
                        to_home_base()
                        Input_Handler.idle_gesture()
                        self.upgrader.collect_resources()

                    if not skip_home_base_upgrades:
                        home_min_time = self.upgrader.run_home_base(exclude_home_base, exclude_home_lab)
                        if home_min_time is not None:
                            if min_completion_time is None or home_min_time < min_completion_time:
                                min_completion_time = home_min_time
                    if not exclude_home_attacks:
                        if configs.USE_TRAINING_POTION and not Task_Handler.magic_items_excluded(use_cached=True):
                            self.upgrader.use_potion("training_potion")
                        self.attacker.run_home_base(restart=not skip_home_base_upgrades or not skip_builder_base_upgrades)

                    # Check builder base
                    if not skip_builder_base_upgrades or not exclude_builder_attacks:
                        to_builder_base()
                        Input_Handler.idle_gesture()

                    if not skip_builder_base_upgrades or not exclude_builder_attacks:
                        self.upgrader.collect_builder_attack_elixir()
                    if not skip_builder_base_upgrades:
                        if configs.USE_BUILDER_POTION and not Task_Handler.magic_items_excluded(use_cached=True):
                            self.upgrader.use_potion("builder_potion")
                        self.upgrader.run_builder_base(exclude_builder_base, exclude_builder_lab)
                    if not exclude_builder_attacks:
                        self.attacker.run_builder_base()

                    to_home_base()
                    Input_Handler.idle_gesture()
                    stop_coc()
                    self.update_status(time.time())

                _err_count = 0
                Input_Handler._ensure_rng()
                
                # Use dynamic CHECK_INTERVAL based on upgrade completion time
                next_interval = CHECK_INTERVAL
                if min_completion_time is not None and min_completion_time < CHECK_INTERVAL:
                    next_interval = min_completion_time
                    logger.info("[Bot] Using dynamic interval: %ds (from upgrade completion time)", next_interval)
                
                jitter = int(Input_Handler.rng.integers(-CHECK_INTERVAL_JITTER, CHECK_INTERVAL_JITTER + 1))
                time.sleep(max(0, next_interval + jitter))

            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                logger.error("%s", e)
                try:
                    stop_coc()
                except (KeyboardInterrupt, SystemExit): raise
                except Exception as se:
                    if configs.DEBUG: logger.debug("stop_coc in error handler failed: %s", se)
                self.update_status("error")
                delay = min(10 * 2 ** _err_count, 300)
                logger.warning("Recovering in %ds (attempt %d)...", delay, _err_count + 1)
                human_delay(delay, spread=0.1)
                try:
                    self._recover()
                    state = self._validate_game_state()
                    if state == "unknown":
                        logger.warning("Unknown game state after recovery, restarting CoC...")
                        stop_coc()
                        if not start_coc():
                            raise Exception("Failed to restart CoC after recovery")
                    elif state == "loading":
                        human_delay(5.0)
                    _err_count = 0
                except (KeyboardInterrupt, SystemExit): raise
                except Exception as re:
                    logger.error("recover: %s", re)
                    _err_count += 1
