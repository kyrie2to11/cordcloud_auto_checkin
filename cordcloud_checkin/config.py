import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def env_value(key: str, default: str = "") -> str:
    """Read an environment variable, treating an empty string as unset."""
    val = os.getenv(key)
    return val if val else default


def env_bool(key: str, default: bool) -> bool:
    default_value = "true" if default else "false"
    return env_value(key, default_value).lower() == "true"


def env_int(key: str, default: int) -> int:
    return int(env_value(key, str(default)))


@dataclass(frozen=True)
class Settings:
    cordcloud_email: str
    cordcloud_password: str
    pop3_host: str
    pop3_port: int
    pop3_use_ssl: bool
    pop3_username: str
    pop3_password: str
    pop3_scan_limit: int
    smtp_host: str
    smtp_port: int
    smtp_use_ssl: bool
    smtp_username: str
    smtp_password: str
    use_persistent_context: bool
    persistent_profile_dir: Path
    headless: bool
    save_html: bool
    debug_html_dir: Path
    login_url: str
    user_url: str


def load_settings() -> Settings:
    env_loaded = load_dotenv()
    if not env_loaded:
        print("[Config] 未找到 .env 文件，使用系统环境变量")

    cordcloud_email = env_value("CORDCLOUD_EMAIL")

    return Settings(
        cordcloud_email=cordcloud_email,
        cordcloud_password=env_value("CORDCLOUD_PASSWORD"),
        pop3_host=env_value("POP3_HOST", "pop.example.com"),
        pop3_port=env_int("POP3_PORT", 995),
        pop3_use_ssl=env_bool("POP3_USE_SSL", True),
        pop3_username=env_value("POP3_USERNAME", cordcloud_email),
        pop3_password=env_value("POP3_PASSWORD"),
        pop3_scan_limit=env_int("POP3_SCAN_LIMIT", 10),
        smtp_host=env_value("SMTP_HOST", "smtp.qq.com"),
        smtp_port=env_int("SMTP_PORT", 465),
        smtp_use_ssl=env_bool("SMTP_USE_SSL", True),
        smtp_username=env_value("SMTP_USERNAME", cordcloud_email),
        smtp_password=env_value("SMTP_PASSWORD"),
        use_persistent_context=env_bool("USE_PERSISTENT_CONTEXT", True),
        persistent_profile_dir=Path(env_value("PERSISTENT_PROFILE_DIR", "./cloak_profile")),
        headless=env_bool("HEADLESS", False),
        save_html=env_bool("SAVE_HTML", True),
        debug_html_dir=Path(env_value("DEBUG_HTML_DIR", "./debug_html")),
        login_url=env_value("LOGIN_URL", "https://www.cordcloud.one/auth/login"),
        user_url=env_value("USER_URL", "https://www.cordcloud.one/user"),
    )
