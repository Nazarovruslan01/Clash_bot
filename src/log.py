import sys
import logging
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="torch")


def setup_logging(instance_id: str, debug: bool) -> None:
    logger = logging.getLogger("coc_bot")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        f"[%(asctime)s] [{instance_id}] [%(levelname)s] %(message)s",
        datefmt="%I:%M:%S %p",
    )

    # Console handler — only in dev mode (not frozen)
    if not getattr(sys, "frozen", False):
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG if debug else logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    # File handler — always, with rotation
    if getattr(sys, "frozen", False):
        log_dir = Path.home() / ".CoC_Bot" / "debug"
    else:
        log_dir = Path("debug")
    log_dir.mkdir(parents=True, exist_ok=True)

    fh = RotatingFileHandler(
        log_dir / f"{instance_id}.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
