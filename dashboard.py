import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st


def safe_p95(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.quantile(0.95))


def fmt(value: float | int | str | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def load_logs_dataframe(db_path: Path) -> tuple[pd.DataFrame | None, str | None]:
    if not db_path.exists():
        return None, "Файл logs.db не найден. Сначала запустите приложение и создайте логи."

    try:
        with sqlite3.connect(db_path) as connection:
            table_check = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='request_logs'",
                connection,
            )
            if table_check.empty:
                return None, "Таблица request_logs не найдена в logs.db."

            df = pd.read_sql_query("SELECT * FROM request_logs", connection)
            return df, None
    except Exception as exc:
        return None, f"Ошибка чтения logs.db: {exc}"


def main() -> None:
    st.set_page_config(
        page_title="Карьерный AI-ассистент — Аналитика",
        layout="wide",
    )

    st.title("Карьерный AI-ассистент\nАналитика и мониторинг системы")
    st.caption("Career AI Assistant — Analytics & Monitoring")

    df, error_message = load_logs_dataframe(Path("logs.db"))
    if error_message:
        st.warning(error_message)
        return

    assert df is not None
    if df.empty:
        st.info("Таблица request_logs пуста. Пока нет данных для анализа.")
        return

    for col in ("provider", "operation", "status"):
        if col not in df.columns:
            df[col] = None
    if "duration_ms" not in df.columns:
        df["duration_ms"] = None

    df["provider"] = df["provider"].fillna("unknown").astype(str)
    df["operation"] = df["operation"].fillna("unknown").astype(str)
    df["status"] = df["status"].fillna("unknown").astype(str)
    df["duration_ms"] = pd.to_numeric(df["duration_ms"], errors="coerce")

    st.sidebar.header("Фильтры")
    provider_options = sorted(df["provider"].dropna().unique().tolist())
    operation_options = sorted(df["operation"].dropna().unique().tolist())

    selected_providers = st.sidebar.multiselect(
        "Провайдер",
        options=provider_options,
        default=provider_options,
    )

    st.sidebar.markdown("### Фильтр по операциям")
    st.sidebar.markdown(
        "<div style='height: 6px;'></div>",
        unsafe_allow_html=True,
    )
    selected_operations = st.sidebar.multiselect(
        "Операция",
        options=operation_options,
        default=operation_options,
        label_visibility="collapsed",
    )
    only_errors = st.sidebar.checkbox("Только ошибки", value=False)

    filtered = df.copy()
    if selected_providers:
        filtered = filtered[filtered["provider"].isin(selected_providers)]
    if selected_operations:
        filtered = filtered[filtered["operation"].isin(selected_operations)]
    if only_errors:
        filtered = filtered[filtered["status"] != "success"]

    if filtered.empty:
        st.info("Нет данных для выбранных фильтров")
        return

    total_requests = int(len(filtered))
    errors_count = int((filtered["status"] != "success").sum())
    duration_series = filtered["duration_ms"].dropna()
    avg_delay = float(duration_series.mean()) if not duration_series.empty else None

    provider_delay = (
        filtered.dropna(subset=["duration_ms"]).groupby("provider")["duration_ms"].mean()
    )
    slowest_provider = provider_delay.idxmax() if not provider_delay.empty else None

    operation_delay = (
        filtered.dropna(subset=["duration_ms"]).groupby("operation")["duration_ms"].mean()
    )
    slowest_operation = operation_delay.idxmax() if not operation_delay.empty else None

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Всего запросов", fmt(total_requests))
    c2.metric("Ошибки", fmt(errors_count))
    c3.metric("Средняя задержка (ms)", fmt(avg_delay))
    c4.metric("Самая медленная операция", fmt(slowest_operation))
    c5.metric("Самый медленный провайдер", fmt(slowest_provider))

    requests_by_provider = filtered.groupby("provider").size().reset_index(name="Количество запросов")
    requests_by_operation = filtered.groupby("operation").size().reset_index(name="Количество запросов")
    delay_source = filtered.dropna(subset=["duration_ms"])

    col_left, col_mid, col_right = st.columns(3)

    with col_left:
        st.subheader("Запросы по провайдерам")
        st.dataframe(requests_by_provider, use_container_width=True, height=280)
        st.caption("Количество запросов по провайдерам")
        st.bar_chart(
            requests_by_provider.set_index("provider")["Количество запросов"],
            use_container_width=True,
            height=220,
        )

    with col_mid:
        st.subheader("Запросы по операциям")
        st.dataframe(requests_by_operation, use_container_width=True, height=280)
        st.caption("Средняя задержка по операциям")
        if delay_source.empty:
            st.info("Нет данных duration_ms для графика по операциям.")
        else:
            avg_delay_operation = delay_source.groupby("operation")["duration_ms"].mean().sort_values()
            st.bar_chart(avg_delay_operation, use_container_width=True, height=220)

    with col_right:
        st.subheader("Сравнение генерации изображений")
        image_df = filtered[
            (filtered["operation"] == "image_generation")
            & (filtered["provider"].isin(["openai", "proxy"]))
        ].dropna(subset=["duration_ms"])
        if image_df.empty:
            st.info("Нет данных для сравнения генерации изображений.")
        else:
            image_stats = (
                image_df.groupby("provider")["duration_ms"]
                .agg(avg="mean", min="min", max="max")
                .reset_index()
            )
            image_p95 = (
                image_df.groupby("provider")["duration_ms"].apply(safe_p95).reset_index(name="p95")
            )
            image_stats = image_stats.merge(image_p95, on="provider", how="left")
            st.dataframe(image_stats, use_container_width=True, height=280)

        st.caption("Средняя задержка по провайдерам")
        if delay_source.empty:
            st.info("Нет данных duration_ms для графика по провайдерам.")
        else:
            avg_delay_provider = delay_source.groupby("provider")["duration_ms"].mean().sort_values()
            st.bar_chart(avg_delay_provider, use_container_width=True, height=220)

    with st.expander("Подробные метрики задержек", expanded=False):
        if delay_source.empty:
            st.info("Нет данных duration_ms для расчета задержек.")
        else:
            delay_table = (
                delay_source.groupby(["provider", "operation"])["duration_ms"]
            .agg(avg="mean", min="min", max="max")
            .reset_index()
        )
            p95_table = (
                delay_source.groupby(["provider", "operation"])["duration_ms"]
                .apply(safe_p95)
                .reset_index(name="p95")
            )
            delay_table = delay_table.merge(
                p95_table, on=["provider", "operation"], how="left"
            ).sort_values(["provider", "operation"])
            st.dataframe(delay_table, use_container_width=True, height=260)

    with st.expander("Последние записи логов", expanded=False):
        if "created_at" in filtered.columns:
            recent_logs = filtered.sort_values("created_at", ascending=False).head(20)
        elif "id" in filtered.columns:
            recent_logs = filtered.sort_values("id", ascending=False).head(20)
        else:
            recent_logs = filtered.head(20)
        st.dataframe(recent_logs, use_container_width=True, height=260)


if __name__ == "__main__":
    main()
