from cordcloud_checkin.browser_flow import run_checkin
from cordcloud_checkin.config import load_settings


def main() -> None:
    settings = load_settings()
    run_checkin(settings)


if __name__ == "__main__":
    main()
