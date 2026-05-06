import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def safe_p95(values: list[int]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return float(ordered[index])


def format_metric(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def main() -> None:
    db_path = Path("logs.db")
    if not db_path.exists():
        print("logs.db not found. Nothing to analyze.")
        return

    try:
        with sqlite3.connect(db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='request_logs'"
            )
            if cursor.fetchone() is None:
                print("Table request_logs not found in logs.db.")
                return

            cursor.execute(
                """
                SELECT provider, operation, duration_ms, status
                FROM request_logs
                """
            )
            rows = cursor.fetchall()
    except Exception as exc:
        print(f"Failed to read logs.db: {exc}")
        return

    total_records = len(rows)
    provider_counts: Counter[str] = Counter()
    operation_counts: Counter[str] = Counter()
    errors_count = 0

    durations_by_provider_operation: dict[tuple[str, str], list[int]] = defaultdict(list)
    durations_by_provider: dict[str, list[int]] = defaultdict(list)
    durations_by_operation: dict[str, list[int]] = defaultdict(list)
    image_generation_by_provider: dict[str, list[int]] = defaultdict(list)

    for provider, operation, duration_ms, status in rows:
        provider_name = provider or "unknown"
        operation_name = operation or "unknown"
        status_value = status or "unknown"

        provider_counts[provider_name] += 1
        operation_counts[operation_name] += 1
        if status_value != "success":
            errors_count += 1

        if duration_ms is None:
            continue

        try:
            duration_int = int(duration_ms)
        except (TypeError, ValueError):
            continue

        durations_by_provider_operation[(provider_name, operation_name)].append(duration_int)
        durations_by_provider[provider_name].append(duration_int)
        durations_by_operation[operation_name].append(duration_int)

        if operation_name == "image_generation":
            image_generation_by_provider[provider_name].append(duration_int)

    print("=== Logs Analysis (request_logs) ===")
    print(f"Total records: {total_records}")
    print("")

    print("Records by provider:")
    if provider_counts:
        for provider_name, count in provider_counts.most_common():
            print(f"- {provider_name}: {count}")
    else:
        print("- no data")
    print("")

    print("Records by operation:")
    if operation_counts:
        for operation_name, count in operation_counts.most_common():
            print(f"- {operation_name}: {count}")
    else:
        print("- no data")
    print("")

    print("Latency by provider + operation (ms):")
    if durations_by_provider_operation:
        for (provider_name, operation_name), values in sorted(
            durations_by_provider_operation.items(), key=lambda item: (item[0][0], item[0][1])
        ):
            avg_value = statistics.mean(values)
            min_value = min(values)
            max_value = max(values)
            p95_value = safe_p95(values)
            print(
                f"- {provider_name} | {operation_name}: "
                f"avg={format_metric(avg_value)}, "
                f"min={format_metric(min_value)}, "
                f"max={format_metric(max_value)}, "
                f"p95={format_metric(p95_value)}"
            )
    else:
        print("- no latency data")
    print("")

    print(f"Errors (status != success): {errors_count}")
    print("")

    print("Image generation comparison (ms):")
    for provider_name in ("openai", "proxy"):
        values = image_generation_by_provider.get(provider_name, [])
        if not values:
            print(f"- {provider_name}: no data")
            continue
        print(
            f"- {provider_name}: "
            f"avg={format_metric(statistics.mean(values))}, "
            f"min={format_metric(min(values))}, "
            f"max={format_metric(max(values))}, "
            f"p95={format_metric(safe_p95(values))}"
        )
    print("")

    slowest_provider = None
    if durations_by_provider:
        slowest_provider = max(
            durations_by_provider.items(),
            key=lambda item: statistics.mean(item[1]),
        )[0]

    slowest_operation = None
    if durations_by_operation:
        slowest_operation = max(
            durations_by_operation.items(),
            key=lambda item: statistics.mean(item[1]),
        )[0]

    print("Summary:")
    print(f"- Slowest provider: {slowest_provider or 'n/a'}")
    print(f"- Slowest operation: {slowest_operation or 'n/a'}")
    print(f"- Errors present: {'yes' if errors_count > 0 else 'no'}")


if __name__ == "__main__":
    main()
