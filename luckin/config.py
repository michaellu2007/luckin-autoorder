"""配置/凭证/日志的统一读取。"""

import logging
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"


def load_config(path=None) -> dict:
    path = pathlib.Path(path) if path else ROOT / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"找不到 {path}\n先把 config.example.yaml 复制为 config.yaml，"
            "填好门店、饮品候选和推送 key"
        )
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_token() -> dict:
    path = ROOT / "token.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"找不到 {path}\n还没有登录凭证，请按 capture_token.md 做一次抓包"
        )
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not data.get("token"):
        raise ValueError("token.yaml 里没有 token，请重新抓包（见 capture_token.md）")
    return data


def save_token(data: dict):
    with open(ROOT / "token.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True)


def load_endpoints() -> dict:
    """抓包解析生成的 endpoints.yaml 优先；没有就用 api.py 里的默认值。"""
    path = ROOT / "endpoints.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_logger(name="luckin") -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    logger.addHandler(logging.FileHandler(LOG_DIR / "run.log", encoding="utf-8"))
    # 计划任务后台运行时可能没有 stdout
    if sys.stdout is not None:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger
