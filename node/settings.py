"""Node settings: defaults, then the repo-root .env, then CLI overrides."""

from dataclasses import dataclass, field, replace
import os
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
DATA_DIR = Path.home() / "icu-data"


class SettingsError(Exception):
    pass


def detect_pi() -> bool:
    try:
        return "Raspberry Pi" in Path("/proc/device-tree/model").read_text(errors="ignore")
    except OSError:
        return False


@dataclass
class Settings:
    broker_host: str = "localhost"
    broker_port: int = 1883
    node_id: str = "bed1"
    node_user: str = "bed1"
    node_pass: str = field(default="", repr=False)
    window_s: float = 3.0
    heartbeat_s: float = 10.0
    keepalive: int = 5
    camera_kind: str = "usb"
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    params_path: Path = REPO_ROOT / "node" / "vision" / "gesture_params.json"
    hand_model_path: Path = DATA_DIR / "models" / "hand_landmarker.task"
    model_path: Path = REPO_ROOT / "ml" / "models" / "model.json"
    replay_dir: Path = REPO_ROOT / "ml" / "replay"
    log_dir: Path = DATA_DIR / "logs"
    on_pi: bool = False

    @classmethod
    def load(cls, env_path: Path | None = None, **overrides) -> "Settings":
        """Defaults that work for VisionFeatureExtractor, updated from .env and overrides."""
        env = {**dotenv_values(env_path or ENV_PATH), **{k: v for k, v in os.environ.items() if k.isupper()}}
        overrides = {k: v for k, v in overrides.items() if v is not None}
        env_node = env.get("NODE_ID") or "bed1"
        env_user = env.get("NODE_USER") or env_node
        node_id = overrides.pop("node_id", env_node)
        node_user = overrides.pop("node_user", env_user if node_id == env_node else node_id)
        s = cls(
            broker_host=env.get("BROKER_HOST") or "localhost",
            broker_port=int(env.get("BROKER_PORT") or 1883),
            node_id=node_id,
            node_user=node_user,
            on_pi=detect_pi(),
        )
        s = replace(s, **overrides)
        s.node_pass = _password_for(env, s.node_user, env_user)
        return s

    def check_broker(self) -> None:
        """Fail clearly before connecting (never prints the password)."""
        if not self.broker_host or self.broker_host == "CHANGE_ME":
            raise SettingsError("BROKER_HOST is not set in .env (run node/tools/set_broker.sh <laptop IP>)")
        if not self.node_pass:
            raise SettingsError(f"no MQTT password for user {self.node_user!r} in .env "
                                f"(NODE_PASS for bed1, BED2_PASS for bed2)")


def _password_for(env: dict, user: str, env_user: str) -> str:
    """NODE_PASS belongs to NODE_USER (bed1); other nodes use <USER>_PASS, e.g. BED2_PASS."""
    if user == env_user and env.get("NODE_PASS"):
        return env["NODE_PASS"]
    return env.get(f"{user.upper()}_PASS") or ""
