# CoC Bot Development Guide

## Project Overview
Automation bot for Clash of Clans game, running on BlueStacks emulator.
- **Stack:** Python 3, ADB (BlueStacks), OpenCV (template matching), Gemini Vision API
- **Core modules:** upgrader.py, attacker.py, coc_bot.py, utils.py
- **Platform:** macOS/Windows with BlueStacks emulator
- **Entry point:** src/main.py (CLI) or src/gui.py (Desktop GUI)

## Architecture

### Module Responsibilities
- **utils.py** - all shared infrastructure: ADB connection, frame capture, template matching, OCR (EasyOCR + Gemini), input simulation (minitouch), anti-detection
- **upgrader.py** - home/builder base upgrade automation (priority-based, parallel checking)
- **attacker.py** - matchmaking, troop deployment, attack completion logic
- **coc_bot.py** - main orchestration loop: manages BlueStacks lifecycle, runs upgrade/attack cycles
- **configs.py** - runtime configuration (user-editable)
- **configs.template.py** - configuration template for new installs (MUST STAY IN SYNC with configs.py)

### Data Flow
1. ADB screenshot → Frame_Handler.get_frame()
2. Template matching (OpenCV) or Gemini Vision for screen recognition
3. Input_Handler sends clicks/swipes via minitouch (with jitter for anti-detection)
4. OCR reads text (EasyOCR local or Gemini fallback)
5. Game state validated, action taken, sleep before next cycle

## Configuration Management

**Critical:** configs.template.py must be kept in sync with configs.py
- New config keys added to configs.py? Add them to configs.template.py with defaults
- Users copy configs.template.py → configs.py, missing keys cause AttributeError at runtime
- Check: grep new keys in both files

**Production setting:** DEBUG = False (currently defaults to False in configs.py)

**BlueStacks integration:**
- Path via configs.BLUESTACKS_PATH (Windows only, macOS uses AppleScript)
- ADB address: typically 127.0.0.1:5555 (configurable via ADB_ADDRESSES)

## Testing & Validation

**Syntax check:**
```bash
python3 -m py_compile src/*.py src/gui_server/*.py app/*.py
```

**Import validation:**
```bash
python3 -c "from src import utils, upgrader, attacker, coc_bot; print('✓ All imports OK')"
```

**No automated test suite yet** — validation is manual/integration before commit

## Common Bugs & Patterns

### Exception Handling
- **Bare except:** blocks catch SystemExit/KeyboardInterrupt — use `except Exception:` instead
- Swallowed errors make debugging hard; log with context when catching

### Configuration Sync
- New AI features (USE_AI_GAME_STATE, etc.) require updates in BOTH configs.py and configs.template.py
- Missing keys in configs.template.py break fresh installs

### Recursion & Loops
- Avoid recursive calls without depth limits (can hit Python stack overflow)
- Use iterative loops with max_retries instead: `for _ in range(max_retries):`
- Example: _validate_game_state() was recursive on dialog/attack states → converted to iterative

### List/Tuple Operations
- Guard before zip(*combined): if combined is empty, zip(*[]) crashes with ValueError
- Check: `if not combined: return None` before `templates, upgrade_text = zip(*combined)`

### Image Handling
- save_frame() must handle both 2D (grayscale) and 3D (RGB) arrays
- cv2.cvtColor(frame, COLOR_RGB2BGR) fails on 2D → check `len(frame.shape) == 2`
- cv2.imread() returns None if file missing → validate before cv2.cvtColor()

### Cooldown/Retry Logic
- When tracking failed upgrades: delete items whose cooldown HAS EXPIRED, not items still cooling down
- Variable naming matters: `upgrades_past_cooldown` not `valid_upgrades` (inverted logic is confusing)

## AI/Gemini Features

**When Enabled:**
- Gemini Vision used for OCR, game state recognition, base analysis, match evaluation
- All Gemini calls in OCR_Handler class (utils.py lines 817–973)
- Rate limit: 10 req/min per user (via check_rate_limit RPC if needed)
- Always validate Gemini response before using (can return None or empty dict)

**Key Methods:**
- `gemini_game_state(frame)` — classify screen into home/builder/attack/loading/dialog/unknown
- `gemini_evaluate_match(frame)` — loot analysis (gold, elixir, dark_elixir, skip boolean)
- `gemini_analyze_base(frame)` — enemy base analysis for attack planning
- `gemini_find_button(frame, description)` — locate button by text description

**Configuration Keys:**
- GEMINI_API_KEY — set via environment or configs.py (leave empty to disable)
- GEMINI_MODEL — default "gemini-2.5-flash"
- USE_AI_GAME_STATE, USE_AI_POPUP_DISMISS, USE_AI_ATTACK_ANALYSIS, USE_AI_MATCH_FILTER — feature flags

## Anti-Detection Mechanisms

All in utils.py Input_Handler class:
- **Jitter:** _jitter() adds Gaussian noise (sigma=0.008) to click coordinates
- **Swipes:** Cubic Bezier curves with random perpendicular control points ±10% duration variation
- **Pressure:** Random touch pressure in range [80, 120]
- **Idle gestures:** ~30% chance of short random swipes between tasks
- **RNG seeding:** reproducible via SESSION_SEED config (None = random)
- **Template-matched clicks:** explicitly pass jitter=False to avoid missing small targets

## Debugging

**Log files:**
- Rotating log file: logs stored via logging.RotatingFileHandler (5MB, 3 backups)
- DEBUG mode: additional frame saves to debug/ directory, verbose logging

**Common issues:**
1. **ADB connection fails** → check BlueStacks running, ADB address in configs
2. **Template matching fails** → frame size mismatch (hardcoded to 1920×1080), asset missing
3. **OCR returns garbage** → use Gemini Vision fallback (USE_AI_GAME_STATE=True)
4. **Bot stuck in dialog loop** → Gemini returns "dialog" repeatedly, max_retries=5 will exit
5. **Cooldown not working** → check upgrade tracking logic (upgrades_past_cooldown deletion)

## Code Review Checklist

Before committing:
- [ ] All imports at module top or clearly scoped (don't hide imports in functions)
- [ ] No bare `except:` — use `except Exception:` or `except SpecificError:`
- [ ] Config keys added? Update BOTH configs.py and configs.template.py
- [ ] Hardcoded paths? Move to configs (e.g., BLUESTACKS_PATH)
- [ ] Recursive loops? Use iterative + max_retries instead
- [ ] Empty list guard before zip/unzip operations
- [ ] Image handling accounts for grayscale (2D) and RGB (3D)
- [ ] Gemini responses validated before use
- [ ] Cooldown/retry logic clear (not inverted)
- [ ] Syntax check passes: `python3 -m py_compile src/*.py`

## Bug Analysis Workflow

When analyzing multiple bugs (10+):
1. **Exploratory phase:** Run parallel Explore agents to identify all issues
2. **Planning phase:** Use Plan Mode (Sonnet) to organize fixes by priority
3. **Implementation phase:** Use code mode (Haiku) for targeted edits
4. **Review phase:** Run /simplify review to catch regressions
5. **Commit phase:** Detail all fixes in commit message (15+ issues = structured list)

This workflow found and fixed 15 critical bugs in one session.

## PR Checklist

- [ ] Branch name: fix/description or feat/description
- [ ] Commit message: concise, lists all fixes
- [ ] 6 files changed max per PR (easier to review)
- [ ] All syntax checks pass
- [ ] No new warnings in imports
- [ ] configs.template.py synced if any config changes
- [ ] DEBUG not accidentally left as True
