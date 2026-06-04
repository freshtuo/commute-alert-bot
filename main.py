"""Small root entry point so local runs and cron stay simple."""

from src.app import main


if __name__ == "__main__":
    raise SystemExit(main())
