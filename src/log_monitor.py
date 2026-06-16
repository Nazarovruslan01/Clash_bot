#!/usr/bin/env python3
"""
Real-time log monitor for priority system validation.
Detects state corruption between GUI exclusions and bot behavior.
"""

import sys
import re
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Expected patterns for priority system correctness
PRIORITY_PATTERNS = {
    "priority_enabled": re.compile(r"home_base_priority.*excluded"),
    "priority_skip": re.compile(r"priority item not found in menu"),
    "random_fallback": re.compile(r"clicking random upgrade"),
    "menu_fail": re.compile(r"(upgrade menu.*failed|menu.*not found|insufficient resources)"),
    "state_error": re.compile(r"(ERROR|Exception|Traceback)"),
}

class LogMonitor:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.last_position = 0
        self.state_history = defaultdict(list)
        self.issues = []
        self.cycle_count = 0

    def read_new_logs(self) -> list[str]:
        """Read only new lines since last read."""
        if not self.log_path.exists():
            return []

        try:
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_position)
                lines = f.readlines()
                self.last_position = f.tell()
            return lines
        except Exception as e:
            print(f"✗ Error reading log: {e}")
            return []

    def analyze_line(self, line: str):
        """Analyze a single log line for issues."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Check for errors
        if PRIORITY_PATTERNS["state_error"].search(line):
            self.issues.append(f"[{timestamp}] ✗ ERROR: {line.strip()}")
            print(f"[{timestamp}] ✗ ERROR DETECTED: {line.strip()}")
            return

        # Track priority skip logs
        if PRIORITY_PATTERNS["priority_skip"].search(line):
            self.state_history["priority_skip"].append((timestamp, line.strip()))
            print(f"[{timestamp}] ⚠ Priority item not found: {line.strip()}")

        # Track menu failures
        if PRIORITY_PATTERNS["menu_fail"].search(line):
            self.state_history["menu_fail"].append((timestamp, line.strip()))
            print(f"[{timestamp}] ⚠ Menu operation failed: {line.strip()}")

        # Track random fallbacks
        if PRIORITY_PATTERNS["random_fallback"].search(line):
            self.state_history["random_fallback"].append((timestamp, line.strip()))
            print(f"[{timestamp}] → Random upgrade (fallback)")

    def detect_state_corruption(self):
        """Detect when GUI state doesn't match bot behavior."""
        priority_skips = len(self.state_history["priority_skip"])
        menu_fails = len(self.state_history["menu_fail"])
        random_fallbacks = len(self.state_history["random_fallback"])

        # Pattern: many priority skips with no menu failures = GUI state mismatch
        if priority_skips > 3 and menu_fails == 0:
            issue = f"✗ CORRUPTION: {priority_skips} priority skips but no menu failures detected. " \
                   f"GUI exclusions may not match actual config."
            self.issues.append(issue)
            print(f"\n{issue}\n")

        # Pattern: all random fallbacks with priority enabled = priority system broken
        if random_fallbacks > 5 and priority_skips == 0:
            issue = f"✗ CORRUPTION: {random_fallbacks} random fallbacks but no priority skips. " \
                   f"Priority system may be disabled in GUI but enabled in config."
            self.issues.append(issue)
            print(f"\n{issue}\n")

        # Pattern: menu fails but then continues with priorities = state inconsistency
        if menu_fails > 0 and priority_skips > 0:
            recent_fail = self.state_history["menu_fail"][-1][0]
            recent_skip = self.state_history["priority_skip"][-1][0]
            print(f"ℹ Menu fail at {recent_fail}, priority skip at {recent_skip}")

    def print_summary(self):
        """Print monitoring summary."""
        print("\n" + "="*60)
        print(f"LOG MONITOR SUMMARY")
        print("="*60)

        if self.state_history["priority_skip"]:
            print(f"\n📊 Priority Skips: {len(self.state_history['priority_skip'])}")
            for ts, msg in self.state_history["priority_skip"][-3:]:  # Last 3
                print(f"  [{ts}] {msg}")

        if self.state_history["menu_fail"]:
            print(f"\n⚠️  Menu Failures: {len(self.state_history['menu_fail'])}")
            for ts, msg in self.state_history["menu_fail"][-3:]:  # Last 3
                print(f"  [{ts}] {msg}")

        if self.state_history["random_fallback"]:
            print(f"\n→ Random Fallbacks: {len(self.state_history['random_fallback'])}")

        if self.issues:
            print(f"\n❌ ISSUES FOUND: {len(self.issues)}")
            for issue in self.issues:
                print(f"  {issue}")
        else:
            print(f"\n✓ No state corruption detected!")

        print("="*60 + "\n")

def find_log_file() -> Path:
    """Find the bot's active log file."""
    # Try common locations
    locations = [
        Path.home() / ".CoC_Bot" / f"{Path.cwd().name}.log",  # Instance-based
        Path.home() / ".CoC_Bot" / "coc_bot.log",
        Path(__file__).parent / "debug" / "main.log",
        Path(__file__).parent / "logs" / "coc_bot.log",
    ]

    for loc in locations:
        if loc.exists():
            return loc

    # If none found, ask user
    print("Log file not found in standard locations.")
    print("Standard locations searched:")
    for loc in locations:
        print(f"  - {loc}")

    custom = input("\nEnter path to log file (or press Enter to exit): ").strip()
    if custom:
        return Path(custom)
    sys.exit(1)

def main():
    log_path = find_log_file()
    print(f"Monitoring log file: {log_path}")
    print("Watching for state corruption in priority system...")
    print("-" * 60)

    monitor = LogMonitor(log_path)

    try:
        while True:
            lines = monitor.read_new_logs()

            if lines:
                for line in lines:
                    monitor.analyze_line(line)

                monitor.detect_state_corruption()
                monitor.cycle_count += 1

            # Print summary every 50 cycles (roughly every 5 minutes)
            if monitor.cycle_count % 50 == 0 and monitor.cycle_count > 0:
                monitor.print_summary()

            time.sleep(6)  # Check logs every 6 seconds

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
        monitor.print_summary()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Monitor error: {e}")
        monitor.print_summary()
        sys.exit(1)

if __name__ == "__main__":
    main()
