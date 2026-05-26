from utils import *
import configs
from configs import *

class Upgrader:

    _WALL_UPGRADE_NAME = "wall"
    _MAX_UPGRADE_RETRIES = 3

    hero_names = [
        "Barbarian King",
        "Archer Queen",
        "Minion Prince",
        "Grand Warden",
        "Royal Champion",
        "Dragon Duke"
    ]
    
    def __init__(self):
        self.assets = Asset_Manager.upgrader_assets

    # ============================================================
    # 📱 Screen Interaction
    # ============================================================
    
    def _click_home_builders(self):
        Input_Handler.click(0.5, 0.05)
    
    def _click_home_lab(self):
        Input_Handler.click(0.4, 0.05)

    def _click_builder_builders(self):
        Input_Handler.click(0.6, 0.05)
    
    def _click_builder_lab(self):
        Input_Handler.click(0.45, 0.05)

    # ============================================================
    # 💰 Resource & Builder Tracking
    # ============================================================

    def home_lab_available(self, timeout=60):
        import time, cv2
        
        start = time.time()
        while time.time() < start + timeout:
            try:
                section = Frame_Handler.get_frame_section(0.368, 0.04, -0.59, 0.08, high_contrast=True)
                if configs.DEBUG: Frame_Handler.save_frame(section, "debug/home_lab.png")
                
                # Find the backslash
                slash = cv2.cvtColor(self.assets["slash"], cv2.COLOR_RGB2GRAY)
                res = cv2.matchTemplate(section, slash, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val < 0.9: continue
                
                # Extract text
                text = fix_digits(''.join(OCR_Handler.get_text(section)).replace(' ', '').replace('/', ''))
                available = int(text[0])
                return available > 0
            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                if configs.DEBUG: print("home_lab_available", e)
            time.sleep(0.5)
        raise Exception("Failed to get home lab availability")

    def builder_lab_available(self, timeout=60):
        import time, cv2
        
        start = time.time()
        while time.time() < start + timeout:
            try:
                section = Frame_Handler.get_frame_section(0.448, 0.04, -0.515, 0.08, high_contrast=True)
                if configs.DEBUG: Frame_Handler.save_frame(section, "debug/builder_lab.png")
                
                # Find the backslash
                slash = cv2.cvtColor(self.assets["slash"], cv2.COLOR_RGB2GRAY)
                res = cv2.matchTemplate(section, slash, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val < 0.9: continue
                
                # Extract text
                text = fix_digits(''.join(OCR_Handler.get_text(section)).replace(' ', '').replace('/', ''))
                available = int(text[0])
                return available > 0
            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                if configs.DEBUG: print("builder_lab_available", e)
            time.sleep(0.5)
        raise Exception("Failed to get builder lab availability")

    def collect_resources(self):
        import time, numpy as np
        try:
            print("  [Home] Collecting resources...")
            Input_Handler.zoom(dir="out")
            time.sleep(0.5)

            # Cover base in two scroll positions: upper half then lower half
            for swipe_n in range(2):
                if swipe_n == 1:
                    Input_Handler.swipe_down()
                    time.sleep(0.3)
                for x in np.linspace(0.2, 0.8, 6):
                    for y in np.linspace(0.25, 0.65, 8):
                        Input_Handler.click(x, y)

            print("  [Home] Resources collected")
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: print("collect_resources", e)

    def collect_builder_attack_elixir(self):
        import time
        
        # Align view to top right corner
        Input_Handler.zoom(dir="out")
        for _ in range(3):
            Input_Handler.swipe_up(
                y1=0.5,
                y2=1.0,
            )
        Input_Handler.swipe_up(
            y1=0.5,
            y2=1.0,
            hold_end_time=500,
        )
        for _ in range(3):
            Input_Handler.swipe_left(
                x1=1.0,
                x2=0.0,
            )
        Input_Handler.swipe_left(
            x1=1.0,
            x2=0.0,
            hold_end_time=500,
        )
        time.sleep(0.5)
        
        # Open elixir cart menu
        Input_Handler.click(0.61, 0.47)
        time.sleep(0.5)
        
        # Collect elixir
        x, y = Frame_Handler.locate(self.assets["collect"], grayscale=False, thresh=0.9)
        if x is not None and y is not None:
            Input_Handler.click(x, y)
            time.sleep(0.1)
        Input_Handler.click_back(3, 0.1)

    # ============================================================
    # 🧱 Upgrade Management
    # ============================================================

    def _get_suggested_upgrade_template(self):
        template = render_text("Suggested upgrades:", "CCBackBeat", 27, color=(211, 253, 127))
        h, w = template.shape[:2]
        return template, w / WINDOW_DIMS[0], h / WINDOW_DIMS[1]

    def _get_other_upgrade_template(self):
        template = render_text("Other upgrades:", "CCBackBeat", 27, color=(211, 253, 127))
        h, w = template.shape[:2]
        return template, w / WINDOW_DIMS[0], h / WINDOW_DIMS[1]

    def _get_upgrade_menu(self, frame, sug_loc, sug_width, return_bounds=False):
        x_sug, y_sug = sug_loc
        menu_top = 0.15
        menu_left = x_sug - 0.5*sug_width
        menu_right = x_sug + 0.5*sug_width + 0.11
        menu = Frame_Handler.crop(frame, menu_left, y_sug, menu_right, 1.0)
        menu_high_contrast = Frame_Handler.high_contrast(menu, thresh=255) / 255
        menu_bottom = y_sug + menu_high_contrast.mean(axis=1).argmax() / WINDOW_DIMS[1]
        menu = Frame_Handler.crop(frame, menu_left, menu_top, menu_right, menu_bottom)
        if return_bounds: return menu, menu_left, menu_top, menu_right, menu_bottom
        return menu

    def _get_potential_upgrade_locs(self, menu):
        import numpy as np
        
        def _mask_color(frame, color, tol=10):
            color = np.array(color).reshape((1, 1, 3))
            mask = (np.abs(frame - color).sum(axis=2) <= tol)
            frame = np.where(mask, 255, 0)
            return frame
        
        def profile_bounds(profile):
            bounds = []
            prev_val = 0
            for i, val in enumerate(profile):
                if prev_val == 0 and val == 1:
                    bounds.append(i)
                if prev_val == 1 and val == 0:
                    bounds.append(i)
                prev_val = val
            if prev_val == 1:
                bounds.append(len(profile))
            bounds = np.array(bounds).reshape((-1, 2))
            centers = (bounds[:, 0] + bounds[:, 1]) / 2
            return bounds, centers
        
        menu_white = _mask_color(menu, [255, 255, 255], tol=0) / 255
        menu_red = _mask_color(menu, (255, 136, 127), tol=10) / 255
        white_profile = np.where(menu_white.mean(axis=1) > 0.01, 1, 0)
        red_profile = np.where(menu_red.mean(axis=1) > 0.01, 1, 0)
        _, white_centers = profile_bounds(white_profile)
        _, red_centers = profile_bounds(red_profile)
        potential_y_locs = [] # in pixels
        for wc in white_centers:
            if len(red_centers) == 0 or abs(red_centers - wc).min() > 12.5:
                potential_y_locs.append(wc)
        return potential_y_locs

    def _find_builder_confirm(self):
        import cv2, numpy as np
        from scipy.ndimage import gaussian_filter1d
        thresh = 0.2
        section = Frame_Handler.get_frame_section(0.0, 0.9, 1.0, 0.92, grayscale=False)
        section = cv2.cvtColor(section, cv2.COLOR_RGB2LAB).astype(np.float32)
        btn_color = cv2.cvtColor(np.array([[[189, 230, 76]]], dtype=np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
        diff = np.linalg.norm((section - btn_color)/255, axis=2).mean(0)
        diff = gaussian_filter1d(diff, sigma=10)
        min_loc = np.argmin(diff)
        x = min_loc / section.shape[1]
        if diff[min_loc] > thresh: return None
        x1 = x
        i = min_loc
        while i > 0 and diff[i] < thresh:
            x1 = i / section.shape[1]
            i -= 1
        x2 = x
        i = min_loc
        while i < section.shape[1]-1 and diff[i] < thresh:
            x2 = i / section.shape[1]
            i += 1
        x = (x1 + x2) / 2
        y = 0.85
        return x, y
    
    def _scroll_locate_upgrade(self, locate_template_func, menu_left, menu_right, menu_top, menu_bottom, dir="down"):
        # First two return values of locate_template_func should be x and y of located template
        import time, numpy as np
        menu_center = (menu_left + menu_right) / 2
        res = locate_template_func()
        if res[0] is None or res[1] is None:
            prev_section = Frame_Handler.get_frame_section(menu_left, menu_top, menu_right, menu_bottom, high_contrast=True, thresh=255)
            for _ in range(20):
                if dir == "down":
                    y1, y2 = menu_bottom-0.05, menu_top+0.05
                elif dir == "up":
                    y1, y2 = menu_top+0.05, menu_bottom-0.05
                Input_Handler.swipe(x1=menu_center, y1=y1, x2=menu_center, y2=y2, duration=0, hold_end_time=100, inter_points=10)
                time.sleep(0.1)
                
                # Check if at end of upgrade menu
                section = Frame_Handler.get_frame_section(menu_left, menu_top, menu_right, menu_bottom, high_contrast=True, thresh=255)
                diff = np.abs(section - prev_section).mean() / 255
                if diff < 0.01: break
                prev_section = section
                
                res = locate_template_func()
                if res[0] is not None and res[1] is not None: break
        return res
    
    @require_exit()
    def _home_upgrade_once(self, upgrade_text=None, exclude_heroes=False):
        import time, re, numpy as np

        try:
            self._click_home_builders()
            time.sleep(0.5)

            sug_template, sug_width, _ = self._get_suggested_upgrade_template()
            x_sug, y_sug = Frame_Handler.locate(sug_template, thresh=0.70, grayscale=False)
            if x_sug is None or y_sug is None: return None
            frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
            _, menu_left, menu_top, menu_right, menu_bottom = self._get_upgrade_menu(frame, (x_sug, y_sug), sug_width, return_bounds=True)
            menu_center = (menu_left + menu_right) / 2

            if configs.START_FROM_MENU_TOP:
                Input_Handler.swipe_up(x=x_sug, y1=y_sug, y2=0.15, duration=0, hold_end_time=100, inter_points=10)
            else:
                for _ in range(5): Input_Handler.swipe_up(x=x_sug, y1=menu_bottom-0.05, y2=0.15, duration=0, hold_end_time=0, inter_points=10)

            if upgrade_text is not None:
                # Specified: find upgrade by text template
                if isinstance(upgrade_text, str): upgrade_text = [upgrade_text]
                if exclude_heroes:
                    upgrade_text = list(set(upgrade_text) - set(self.hero_names))
                templates = [render_text(text, "CCBackBeat", 27) for text in upgrade_text]
                combined = list(zip(templates, upgrade_text))
                templates, upgrade_text = zip(*combined)

                def locate_template(templates, names):
                    frame = Frame_Handler.get_frame(grayscale=False)
                    frame_gray = Frame_Handler.grayscale(frame)
                    _, y_sug_cur = Frame_Handler.locate(sug_template, frame, thresh=0.70, grayscale=False)
                    res = Frame_Handler.batch_locate(templates, frame_gray, thresh=0.80, ref="lc", return_all=True)
                    for items, name in zip(res, names):
                        for x, y in items:
                            if x is not None and y is not None and (y_sug_cur is None or y > y_sug_cur):
                                section = Frame_Handler.crop(frame, menu_left, y-0.02, menu_right, y+0.02)
                                if not check_color((255, 136, 127), section, tol=10):
                                    if abs(x - menu_left) < 0.01:
                                        return x, y, name
                                    new_x, new_y = Frame_Handler.locate(render_text("New", "CCBackBeat", 27, color=(13, 255, 13)), filter_color((13, 255, 13), section), thresh=0.70, grayscale=False, ref="rc")
                                    if new_x is not None and new_y is not None and abs(x - (menu_left + new_x/section.shape[1])) < 0.05:
                                        return x, y, name
                    return None, None, None

                x, y, _ = self._scroll_locate_upgrade(
                    lambda: locate_template(templates, upgrade_text),
                    menu_left, menu_right, menu_top, menu_bottom,
                    dir="down" if configs.START_FROM_MENU_TOP else "up",
                )
                if x is None or y is None:
                    if configs.DEBUG: print(f"_home_upgrade_once: priority item not found in menu ({upgrade_text})")
                    return None
                Input_Handler.click(x_sug, y)
            else:
                # Random: find upgrade by visual analysis
                menu = Frame_Handler.get_frame_section(menu_left, menu_top, menu_right, menu_bottom, grayscale=False)
                frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
                potential_y_locs = self._get_potential_upgrade_locs(menu)
                if configs.DEBUG: print(f"_home_upgrade_once: {len(potential_y_locs)} potential random upgrade rows")
                town_hall_template = [render_text("Town Hall", "CCBackBeat", 27)]
                hero_templates = [render_text(hero, "SupercellMagic", 19) for hero in self.hero_names]
                locs = Frame_Handler.batch_locate(town_hall_template + hero_templates, thresh=0.80, ref="lc", null_val=-1)
                town_hall_loc = locs[0]
                hero_locs = locs[1:]
                invalid_locs = [town_hall_loc]
                if Task_Handler.heroes_excluded():
                    invalid_locs += hero_locs
                invalid_y_locs = np.array(invalid_locs)[:, 1]

                x_upgrade, y_upgrade = None, None
                for y_loc in np.random.permutation(potential_y_locs):
                    y = menu_top + y_loc / WINDOW_DIMS[1]
                    if min(abs(invalid_y_locs - y)) > 0.02:
                        x_upgrade = menu_center
                        y_upgrade = y
                        break
                if x_upgrade is None or y_upgrade is None:
                    if len(potential_y_locs) > 0 and invalid_y_locs[0] != -1 and min(abs(town_hall_loc[1] - np.array(potential_y_locs))) < 0.02:
                        x_upgrade, y_upgrade = menu_center, town_hall_loc[1]
                    else:
                        if configs.DEBUG: print("_home_upgrade_once: no valid random upgrade row found")
                        return None
                if configs.DEBUG: print(f"_home_upgrade_once: clicking random upgrade at ({x_upgrade:.3f}, {y_upgrade:.3f})")
                Input_Handler.click(x_upgrade, y_upgrade)

            time.sleep(0.5)

            # Hero upgrades go directly to confirm screen
            in_hero_hall = not get_home_builders(0, return_amount=False, raise_exception=False)
            if in_hero_hall:
                if Task_Handler.heroes_excluded(): return None
            else:
                self._click_home_builders()
                time.sleep(0.5)
                x, y = Frame_Handler.locate(self.assets["upgrade"], thresh=0.90, grayscale=False)
                if x is None or y is None:
                    if configs.DEBUG: print("_home_upgrade_once: upgrade button not found after selecting building")
                    return None
                Input_Handler.click(x, y)
                time.sleep(0.5)

            x, y = Frame_Handler.locate(self.assets["upgrade_name"], ref="lc", thresh=0.9)
            if x is None or y is None:
                if configs.DEBUG: print("_home_upgrade_once: upgrade_name label not found")
                return None
            section = Frame_Handler.get_frame_section(x+0.122, y-0.04, 1-x, y+0.035, high_contrast=True, thresh=255, use_cached=True)
            if configs.DEBUG: Frame_Handler.save_frame(section, "debug/upgrade_name.png")
            text_list = OCR_Handler.get_text(section)
            if not text_list:
                if configs.DEBUG: print("_home_upgrade_once: OCR returned empty text for upgrade name")
                return None
            upgrade_name = spell_check(re.sub(r"\s*x\d+$", "", text_list[0].lower()[:-3]))

            x, y = Frame_Handler.locate(self.assets["confirm"], grayscale=False, thresh=0.85, use_cached=True)
            if x is None or y is None:
                if configs.DEBUG: print("_home_upgrade_once: confirm button not found")
                return None
            Input_Handler.click(x, y+0.05)
            time.sleep(0.5)
            return upgrade_name
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: print("_home_upgrade_once exception:", e)
            return None

    @require_exit()
    def home_upgrade(self, exclude_heroes=False):
        if not Task_Handler.home_base_priority_excluded():
            for priority_level in configs.HOME_BASE_UPGRADE_PRIORITY:
                upgrade_name = self._home_upgrade_once(priority_level, exclude_heroes=exclude_heroes)
                if upgrade_name is not None: return upgrade_name
        return self._home_upgrade_once(exclude_heroes=exclude_heroes)
    
    @require_exit()
    def assign_builder_apprentice(self):
        import time
        
        try:
            # Open upgrade list menu
            self._click_home_builders()
            time.sleep(0.5)
            
            # Find assistant available label
            xys = Frame_Handler.locate(self.assets["assistant_available"], thresh=0.8, return_all=True)
            xys = sorted(xys, key=lambda pair: pair[1])
            if len(xys) == 0: return
            x, y = xys[0]

            Input_Handler.click(x, y)
            time.sleep(0.5)
            
            # Find assign assistant label
            xys = Frame_Handler.locate(self.assets["assign_assistant"], thresh=0.9, grayscale=False, return_all=True)
            if xys is None: return
            
            x, y = sorted(xys, key=lambda pair: pair[1])[0]
            
            Input_Handler.click(x, y)
            time.sleep(0.5)
            
            # Find confirm button
            x, y = Frame_Handler.locate(self.assets["confirm_assistant"], grayscale=False, thresh=0.9)
            if x is None or y is None: return
            
            Input_Handler.click(x, y)
            time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: print("assign_builder_apprentice", e)
    
    @require_exit()
    def _home_lab_upgrade_once(self, upgrade_text=None):
        import time, re, numpy as np

        try:
            self._click_home_lab()
            time.sleep(0.5)

            sug_template, sug_width, _ = self._get_suggested_upgrade_template()
            x_sug, y_sug = Frame_Handler.locate(sug_template, thresh=0.70, grayscale=False)
            if x_sug is None or y_sug is None: return None
            frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
            _, menu_left, menu_top, menu_right, menu_bottom = self._get_upgrade_menu(frame, (x_sug, y_sug), sug_width, return_bounds=True)
            menu_center = (menu_left + menu_right) / 2

            if configs.START_FROM_MENU_TOP:
                Input_Handler.swipe_up(x=x_sug, y1=y_sug, y2=0.15, duration=0, hold_end_time=100, inter_points=10)
            else:
                for _ in range(5): Input_Handler.swipe_up(x=x_sug, y1=menu_bottom-0.05, y2=0.15, duration=0, hold_end_time=0, inter_points=10)

            if upgrade_text is not None:
                # Specified: find upgrade by text template
                if isinstance(upgrade_text, str): upgrade_text = [upgrade_text]
                templates = [render_text(text, "CCBackBeat", 27) for text in upgrade_text]

                def locate_template(templates):
                    frame = Frame_Handler.get_frame(grayscale=False)
                    frame_gray = Frame_Handler.grayscale(frame)
                    _, y_sug_cur = Frame_Handler.locate(sug_template, frame, thresh=0.70, grayscale=False)
                    xys = Frame_Handler.batch_locate(templates, frame_gray, thresh=0.80, ref="lc")
                    for x, y in xys:
                        if x is not None and y is not None and (y_sug_cur is None or y > y_sug_cur):
                            section = Frame_Handler.crop(frame, menu_left, y-0.02, menu_right, y+0.02)
                            if not check_color((255, 136, 127), section, tol=10):
                                if abs(x - menu_left) < 0.01:
                                    return x, y
                                new_x, new_y = Frame_Handler.locate(render_text("New", "CCBackBeat", 27, color=(13, 255, 13)), filter_color((13, 255, 13), section), thresh=0.70, grayscale=False, ref="rc")
                                if configs.DEBUG: print(menu_left, x, menu_right, y)
                                if new_x is not None and new_y is not None and abs(x - (menu_left + new_x/section.shape[1])) < 0.05:
                                    return x, y
                    return None, None

                x, y = self._scroll_locate_upgrade(
                    lambda: locate_template(templates),
                    menu_left, menu_right, menu_top, menu_bottom,
                    dir="down" if configs.START_FROM_MENU_TOP else "up",
                )
                if x is None or y is None: return None
                Input_Handler.click(x, y)
            else:
                # Random: find upgrade by visual analysis
                menu = Frame_Handler.get_frame_section(menu_left, menu_top, menu_right, menu_bottom, grayscale=False)
                frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
                potential_y_locs = self._get_potential_upgrade_locs(menu)
                if len(potential_y_locs) == 0: return None
                x_upgrade = menu_center
                y_upgrade = menu_top + np.random.choice(potential_y_locs) / WINDOW_DIMS[1]
                Input_Handler.click(x_upgrade, y_upgrade)

            time.sleep(0.5)

            x, y = Frame_Handler.locate(self.assets["upgrade_name"], ref="lc", thresh=0.9)
            if x is None or y is None:
                return None
            section = Frame_Handler.get_frame_section(x+0.122, y-0.04, 1-x, y+0.035, high_contrast=True, thresh=255, use_cached=True)
            if configs.DEBUG: Frame_Handler.save_frame(section, "debug/lab_upgrade_name.png")
            text_list = OCR_Handler.get_text(section)
            if not text_list:
                return None
            upgrade_name = spell_check(re.sub(r"\s*x\d+$", "", text_list[0].lower()[:-3]))

            x, y = Frame_Handler.locate(self.assets["confirm"], grayscale=False, thresh=0.85, use_cached=True)
            if x is None or y is None: return None
            section = Frame_Handler.get_frame_section(x-0.08, y+0.02, x+0.08, y+0.1, grayscale=False, thresh=255, use_cached=True)
            if configs.DEBUG: Frame_Handler.save_frame(section, "debug/lab_upgrade_cost.png")
            if check_color((255, 136, 127), section, tol=10): return None
            Input_Handler.click(x, y+0.05)
            time.sleep(0.5)
            return upgrade_name
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: print("_home_lab_upgrade_once", e)
            return None

    @require_exit()
    def home_lab_upgrade(self):
        if not Task_Handler.home_lab_priority_excluded():
            for priority_level in configs.HOME_LAB_UPGRADE_PRIORITY:
                upgrade_name = self._home_lab_upgrade_once(priority_level)
                if upgrade_name is not None: return upgrade_name
        return self._home_lab_upgrade_once()

    @require_exit()
    def assign_lab_assistant(self):
        import time
        
        try:
            # Open upgrade list menu
            self._click_home_lab()
            time.sleep(0.5)
            
            # Find assistant available label
            xys = Frame_Handler.locate(self.assets["assistant_available"], thresh=0.8, return_all=True)
            xys = sorted(xys, key=lambda pair: pair[1])
            if len(xys) == 0: return
            x, y = xys[0]
            
            Input_Handler.click(x, y)
            time.sleep(0.5)
            
            # Find assign assistant label
            xys = Frame_Handler.locate(self.assets["assign_assistant"], thresh=0.9, grayscale=False, return_all=True)
            if xys is None: return
            
            x, y = sorted(xys, key=lambda pair: pair[1])[0]
            
            Input_Handler.click(x, y)
            time.sleep(0.5)
            
            # Find confirm button
            x, y = Frame_Handler.locate(self.assets["confirm_assistant"], grayscale=False, thresh=0.9)
            if x is None or y is None: return
            
            Input_Handler.click(x, y)
            time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: print("assign_lab_assistant", e)
    
    @require_exit()
    def _builder_upgrade_once(self, upgrade_text=None):
        import time, re, numpy as np

        try:
            self._click_builder_builders()
            time.sleep(0.5)

            sug_template, sug_width, _ = self._get_suggested_upgrade_template()
            x_sug, y_sug = Frame_Handler.locate(sug_template, thresh=0.70, grayscale=False)
            if x_sug is None or y_sug is None: return None
            frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
            _, menu_left, menu_top, menu_right, menu_bottom = self._get_upgrade_menu(frame, (x_sug, y_sug), sug_width, return_bounds=True)
            menu_center = (menu_left + menu_right) / 2

            if configs.START_FROM_MENU_TOP:
                Input_Handler.swipe_up(x=x_sug, y1=y_sug, y2=0.15, duration=0, hold_end_time=100, inter_points=10)
            else:
                for _ in range(5): Input_Handler.swipe_up(x=x_sug, y1=menu_bottom-0.05, y2=0.15, duration=0, hold_end_time=0, inter_points=10)

            if upgrade_text is not None:
                # Specified: find upgrade by text template
                if isinstance(upgrade_text, str): upgrade_text = [upgrade_text]
                templates = [render_text(text, "CCBackBeat", 27) for text in upgrade_text]
                combined = list(zip(templates, upgrade_text))
                templates, upgrade_text = zip(*combined)

                def locate_template(templates, names):
                    frame = Frame_Handler.get_frame(grayscale=False)
                    frame_gray = Frame_Handler.grayscale(frame)
                    _, y_sug_cur = Frame_Handler.locate(sug_template, frame, thresh=0.70, grayscale=False)
                    xys = Frame_Handler.batch_locate(templates, frame_gray, thresh=0.80, ref="lc")
                    for (x, y), name in zip(xys, names):
                        if x is not None and y is not None and (y_sug_cur is None or y > y_sug_cur):
                            section = Frame_Handler.crop(frame, menu_left, y-0.02, menu_right, y+0.02)
                            if not check_color((255, 136, 127), section, tol=10):
                                if abs(x - menu_left) < 0.01:
                                    return x, y, name
                                new_x, new_y = Frame_Handler.locate(render_text("New", "CCBackBeat", 27, color=(13, 255, 13)), filter_color((13, 255, 13), section), thresh=0.70, grayscale=False, ref="rc")
                                if new_x is not None and new_y is not None and abs(x - (menu_left + new_x/section.shape[1])) < 0.05:
                                    return x, y, name
                    return None, None, None

                x, y, upgrade_name = self._scroll_locate_upgrade(
                    lambda: locate_template(templates, upgrade_text),
                    menu_left, menu_right, menu_top, menu_bottom,
                    dir="down" if configs.START_FROM_MENU_TOP else "up",
                )
                if x is None or y is None: return None
                Input_Handler.click(x, y)
            else:
                # Random: read name from menu item, then click
                menu_snap = Frame_Handler.get_frame_section(menu_left, menu_top, menu_right, menu_bottom, grayscale=False)
                frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
                potential_y_locs = self._get_potential_upgrade_locs(menu_snap)
                if len(potential_y_locs) == 0: return None
                x_upgrade = menu_center
                y_upgrade = menu_top + np.random.choice(potential_y_locs) / WINDOW_DIMS[1]
                section = Frame_Handler.high_contrast(Frame_Handler.crop(frame, menu_left, y_upgrade - 0.035, menu_center, y_upgrade + 0.025))
                text_list = OCR_Handler.get_text(section)
                if not text_list:
                    return None
                upgrade_name = spell_check(re.sub(r"\s*x\d+$", "", text_list[0].lower()))
                Input_Handler.click(x_upgrade, y_upgrade)

            time.sleep(0.5)
            self._click_builder_builders()
            time.sleep(0.5)

            x, y = Frame_Handler.locate(self.assets["upgrade"], thresh=0.90, grayscale=False)
            if x is None or y is None: return None
            Input_Handler.click(x, y)
            time.sleep(0.5)

            confirm = self._find_builder_confirm()
            if confirm is None: return None
            Input_Handler.click(*confirm)
            time.sleep(0.5)
            return upgrade_name
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: print("_builder_upgrade_once", e)
            return None

    @require_exit()
    def builder_upgrade(self):
        if not Task_Handler.builder_base_priority_excluded():
            for priority_level in configs.BUILDER_BASE_UPGRADE_PRIORITY:
                upgrade_name = self._builder_upgrade_once(priority_level)
                if upgrade_name is not None: return upgrade_name
        return self._builder_upgrade_once()
    
    @require_exit()
    def _builder_lab_upgrade_once(self, upgrade_text=None):
        import time, re, numpy as np

        try:
            self._click_builder_lab()
            time.sleep(0.5)

            sug_template, sug_width, _ = self._get_suggested_upgrade_template()
            x_sug, y_sug = Frame_Handler.locate(sug_template, thresh=0.70, grayscale=False)
            if x_sug is None or y_sug is None: return None
            frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
            _, menu_left, menu_top, menu_right, menu_bottom = self._get_upgrade_menu(frame, (x_sug, y_sug), sug_width, return_bounds=True)
            menu_center = (menu_left + menu_right) / 2

            if configs.START_FROM_MENU_TOP:
                Input_Handler.swipe_up(x=x_sug, y1=y_sug, y2=0.15, duration=0, hold_end_time=100, inter_points=10)
            else:
                for _ in range(5): Input_Handler.swipe_up(x=x_sug, y1=menu_bottom-0.05, y2=0.15, duration=0, hold_end_time=0, inter_points=10)

            if upgrade_text is not None:
                # Specified: find upgrade by text template
                if isinstance(upgrade_text, str): upgrade_text = [upgrade_text]
                templates = [render_text(text, "CCBackBeat", 27) for text in upgrade_text]
                combined = list(zip(templates, upgrade_text))
                templates, upgrade_text = zip(*combined)

                def locate_template(templates, names):
                    frame = Frame_Handler.get_frame(grayscale=False)
                    frame_gray = Frame_Handler.grayscale(frame)
                    _, y_sug_cur = Frame_Handler.locate(sug_template, frame, thresh=0.70, grayscale=False)
                    xys = Frame_Handler.batch_locate(templates, frame_gray, thresh=0.80, ref="lc")
                    for (x, y), name in zip(xys, names):
                        if x is not None and y is not None and (y_sug_cur is None or y > y_sug_cur):
                            section = Frame_Handler.crop(frame, menu_left, y-0.02, menu_right, y+0.02)
                            if not check_color((255, 136, 127), section, tol=10):
                                if abs(x - menu_left) < 0.01:
                                    return x, y, name
                                new_x, new_y = Frame_Handler.locate(render_text("New", "CCBackBeat", 27, color=(13, 255, 13)), filter_color((13, 255, 13), section), thresh=0.70, grayscale=False, ref="rc")
                                if new_x is not None and new_y is not None and abs(x - (menu_left + new_x/section.shape[1])) < 0.05:
                                    return x, y, name
                    return None, None, None

                x, y, upgrade_name = self._scroll_locate_upgrade(
                    lambda: locate_template(templates, upgrade_text),
                    menu_left, menu_right, menu_top, menu_bottom,
                    dir="down" if configs.START_FROM_MENU_TOP else "up",
                )
                if x is None or y is None: return None
                Input_Handler.click(x, y)
            else:
                # Random: read name from menu item, then click
                menu_snap = Frame_Handler.get_frame_section(menu_left, menu_top, menu_right, menu_bottom, grayscale=False)
                frame = Frame_Handler.get_frame(grayscale=False, use_cached=True)
                potential_y_locs = self._get_potential_upgrade_locs(menu_snap)
                if len(potential_y_locs) == 0: return None
                x_upgrade = menu_center
                y_upgrade = menu_top + np.random.choice(potential_y_locs) / WINDOW_DIMS[1]
                section = Frame_Handler.high_contrast(Frame_Handler.crop(frame, menu_left, y_upgrade - 0.035, menu_center, y_upgrade + 0.025))
                text_list = OCR_Handler.get_text(section)
                if not text_list:
                    return None
                upgrade_name = spell_check(re.sub(r"\s*x\d+$", "", text_list[0].lower()))
                Input_Handler.click(x_upgrade, y_upgrade)

            time.sleep(0.5)

            confirm = self._find_builder_confirm()
            if confirm is None: return None
            Input_Handler.click(*confirm)
            time.sleep(0.5)
            return upgrade_name
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as e:
            if configs.DEBUG: print("_builder_lab_upgrade_once", e)
            return None

    @require_exit()
    def builder_lab_upgrade(self):
        if not Task_Handler.builder_lab_priority_excluded():
            for priority_level in configs.BUILDER_LAB_UPGRADE_PRIORITY:
                upgrade_name = self._builder_lab_upgrade_once(priority_level)
                if upgrade_name is not None: return upgrade_name
        return self._builder_lab_upgrade_once()
    
    # ============================================================
    # 📡 Upgrade Monitoring
    # ============================================================
    
    def run_home_base(self, exclude_base=False, exclude_lab=False):
        import time

        Input_Handler.zoom(dir="out")
        Input_Handler.swipe_down()

        exclude_heroes = Task_Handler.heroes_excluded()

        # Building upgrades
        upgrades_started = []
        if not exclude_base:
            counter = 0
            retry_count = 0
            while counter < MAX_UPGRADES_PER_CHECK:
                counter += 1
                try:
                    initial_builders = get_home_builders(1)
                    if initial_builders <= max(0, OPEN_HOME_BUILDERS): break
                    upgraded = self.home_upgrade(exclude_heroes=exclude_heroes)
                    time.sleep(0.5)
                    final_builders = get_home_builders(1)
                    if upgraded is not None:
                        upgraded = upgraded.lower()
                        if final_builders < initial_builders:
                            upgrades_started.append(upgraded)
                            retry_count = 0
                        elif final_builders == initial_builders and upgraded != self._WALL_UPGRADE_NAME:
                            retry_count += 1
                            if retry_count >= self._MAX_UPGRADE_RETRIES:
                                retry_count = 0
                                continue
                            time.sleep(1)
                        else:
                            retry_count = 0
                    else: break
                except (KeyboardInterrupt, SystemExit): raise
                except Exception as e:
                    if configs.DEBUG: print("run_home_base upgrade loop:", e)
        if not Task_Handler.builder_apprentice_excluded():
            self.assign_builder_apprentice()
        
        # Lab upgrades
        lab_upgrades_started = []
        try:
            if not exclude_lab and self.home_lab_available(1):
                upgraded = self.home_lab_upgrade()
                time.sleep(0.5)
                final_lab_avail = self.home_lab_available(1)
                if upgraded is not None and not final_lab_avail: lab_upgrades_started.append(upgraded.lower())
        except (KeyboardInterrupt, SystemExit): raise
        except: pass
        if not Task_Handler.lab_assistant_excluded():
            self.assign_lab_assistant()
        
        if upgrades_started:
            print(f"  [Home] Upgraded: {', '.join(upgrades_started)}")
        else:
            print("  [Home] No building upgrades started")
        if lab_upgrades_started:
            print(f"  [Home Lab] Upgraded: {', '.join(lab_upgrades_started)}")
        else:
            print("  [Home Lab] No lab upgrade started")
        for upgrade in upgrades_started + lab_upgrades_started:
            send_notification(f"Started upgrading {upgrade}")

    def run_builder_base(self, exclude_base=False, exclude_lab=False):
        import time
        
        Input_Handler.zoom(dir="out")
        Input_Handler.swipe_down()
        
        # Building upgrades
        upgrades_started = []
        if not exclude_base:
            counter = 0
            retry_count = 0
            while counter < MAX_UPGRADES_PER_CHECK:
                counter += 1
                try:
                    initial_builders = get_builder_builders(1)
                    if initial_builders <= max(0, OPEN_BUILDER_BUILDERS): break
                    upgraded = self.builder_upgrade()
                    time.sleep(0.5)
                    final_builders = get_builder_builders(1)
                    if upgraded is not None:
                        upgraded = upgraded.lower()
                        if final_builders < initial_builders:
                            upgrades_started.append(upgraded)
                            retry_count = 0
                        elif final_builders == initial_builders and upgraded != self._WALL_UPGRADE_NAME:
                            retry_count += 1
                            if retry_count >= self._MAX_UPGRADE_RETRIES:
                                retry_count = 0
                                continue
                            time.sleep(1)
                        else:
                            retry_count = 0
                    else: break
                except (KeyboardInterrupt, SystemExit): raise
                except Exception as e:
                    if configs.DEBUG: print("run_builder_base upgrade loop:", e)

        # Lab upgrades
        lab_upgrades_started = []
        try:
            if not exclude_lab and self.builder_lab_available(1):
                upgraded = self.builder_lab_upgrade()
                time.sleep(0.5)
                final_lab_avail = self.builder_lab_available(1)
                if upgraded is not None and not final_lab_avail: lab_upgrades_started.append(upgraded.lower())
        except (KeyboardInterrupt, SystemExit): raise
        except: pass

        if upgrades_started:
            print(f"  [Builder] Upgraded: {', '.join(upgrades_started)}")
        else:
            print("  [Builder] No building upgrades started")
        if lab_upgrades_started:
            print(f"  [Builder Lab] Upgraded: {', '.join(lab_upgrades_started)}")
        else:
            print("  [Builder Lab] No lab upgrade started")
        for upgrade in upgrades_started + lab_upgrades_started:
            send_notification(f"Started upgrading {upgrade}")