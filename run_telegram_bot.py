import sys
import traceback

from interfaces import telegram_bot


def main() -> None:
    try:
        telegram_bot.run_polling()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(
            f"run_telegram_bot: fatal error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        traceback.print_exc()
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
