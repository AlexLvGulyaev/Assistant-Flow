import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.telegram_formatter import format_for_telegram


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        # Keep compatibility with environments where reconfigure is unavailable.
        pass

    source = (
        "$$\n"
        "6\\mathrm{H_2O} + 6\\mathrm{CO_2} + \\text{световая энергия}"
        "\\rightarrow\\mathrm{C_6H_{12}O_6}+6\\mathrm{O_2}\n"
        "$$"
    )
    result = format_for_telegram(source)
    print(result)


if __name__ == "__main__":
    main()
