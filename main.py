import sys

from cordcloud_checkin.browser_flow import run_checkin
from cordcloud_checkin.config import load_settings


def main() -> int:
    settings = load_settings()
    return 0 if run_checkin(settings) else 1


if __name__ == "__main__":
    sys.exit(main())
