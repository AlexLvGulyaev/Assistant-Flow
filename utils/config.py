import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv


def _load_dotenv(dotenv_path: str = ".env") -> Dict[str, str]:
    """Load .env into process environment without external dependencies."""
    env_map: Dict[str, str] = {}
    path = Path(dotenv_path)
    if not path.exists():
        return env_map

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env_map[key] = value
        if key not in os.environ:
            os.environ[key] = value
    return env_map


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    gigachat_auth_key: str
    gigachat_scope: str
    gigachat_model: str
    gigachat_max_tokens: int
    openai_api_key: str
    openai_model: str
    openai_image_model: str
    proxy_api_key: str
    proxy_openai_base_url: Optional[str]
    proxy_image_model: str
    image_provider: str = "proxy"
    logs_db_path: str = "logs.db"
    timeout_seconds: int = 30
    chroma_persist_dir: str = "data/chroma_db"
    rag_documents_dir: str = "data/documents"
    rag_top_k: int = 3
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 200
    rag_answer_max_tokens: int = 1500
    openai_base_url: Optional[str] = None
    openai_embedding_model: str = "text-embedding-3-small"
    rag_embedding_request_timeout: float = 30.0
    rag_retrieval_timeout: int = 60
    rag_max_distance: float = 1.38
    # Heavy RAG safeguards: cap на размер загружаемого/индексируемого документа (MB).
    # Защита RAM VPS: большой файл больше не читается целиком в память admin-api.
    admin_upload_max_mb: int = 25
    chroma_use_http: bool = False
    chroma_host: str = "127.0.0.1"
    chroma_port: int = 8000
    # PostgreSQL: same source as os.environ DATABASE_URL after load_dotenv (see repositories.connection).
    database_url: Optional[str] = None
    # P6.1 / P6.2a: chroma по умолчанию; faiss — только явный RAG_BACKEND=faiss (secondary demo).
    rag_backend: str = "chroma"
    # P6.4: hybrid KB + dialog memory в RAG только при true и переданном hybrid_session_id.
    enable_hybrid_retrieval: bool = False
    # P6.5: offline RAG evaluation; RAGAS опционален, по умолчанию выключен.
    enable_ragas_evaluation: bool = False
    rag_eval_dataset_path: str = "evaluation/datasets/rag_smoke_dataset.json"
    rag_eval_output_dir: str = "outputs/evaluation"
    # P6.6: локальный SQLite cache (не PostgreSQL SoT); retrieval/answer по умолчанию выключены.
    cache_db_path: str = "storage/cache/assistant_cache.sqlite3"
    enable_retrieval_cache: bool = False
    enable_answer_cache: bool = False
    retrieval_cache_ttl_seconds: int = 86_400
    answer_cache_ttl_seconds: int = 86_400
    # Изолированное хранилище FAISS (не Chroma, не PostgreSQL lifecycle).
    faiss_index_dir: str = "storage/faiss"
    # P6.9: Weaviate (local / compose); vectors supplied by AF (OpenAI embeddings), not server vectorizer.
    weaviate_url: str = ""
    weaviate_host: str = "weaviate"
    weaviate_http_port: int = 8080
    weaviate_grpc_port: int = 50051
    weaviate_class_name: str = "AssistantFlowChunk"
    asset_storage_backend: str = "filesystem"
    asset_storage_dir: str = "/app/storage/assets"
    audio_enabled: bool = True
    stt_provider: str = "disabled"
    tts_provider: str = "disabled"
    audio_storage_namespace: str = "audio"
    stt_model: str = "whisper-1"
    audio_max_bytes: int = 20 * 1024 * 1024
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_output_format: str = "mp3"
    tts_max_chars: int = 3000
    # Audio hardening / cost accounting (P5.4 remainder).
    audio_timeout_seconds: int = 60
    audio_max_retries: int = 1
    stt_cost_per_minute_usd: float = 0.006
    tts_cost_per_1m_chars_usd: float = 15.0
    # Memory v1: Telegram RAG short-term dialog в PostgreSQL (chat_sessions / chat_messages).
    telegram_pg_conversation_memory: bool = True
    telegram_memory_max_turn_pairs: int = 6
    telegram_memory_max_llm_messages: int = 24
    # Memory v1.1: отдельный лимит символов на хвост диалога в RAG LLM (не retrieval).
    rag_conversation_history_max_chars: int = 12000
    # Зарезервировано: idle timeout сессии (секунды); 0 = не используется в рантайме.
    chat_session_idle_timeout_seconds: int = 0

    @property
    def token_url(self) -> str:
        return "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    @property
    def prompt_url(self) -> str:
        return "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


def load_config() -> AppConfig:
    load_dotenv()
    _load_dotenv()

    max_tokens_raw = os.getenv("GIGACHAT_MAX_TOKENS", "512")
    try:
        max_tokens = int(max_tokens_raw)
    except ValueError:
        max_tokens = 512

    def _int_env(name: str, default: int) -> int:
        raw = os.getenv(name, str(default))
        try:
            return int(raw)
        except ValueError:
            return default

    def _float_env(name: str, default: float) -> float:
        raw = os.getenv(name, str(default))
        try:
            return float(raw)
        except ValueError:
            return default

    def _optional_stripped_url(
        name: str,
        *,
        default_if_unset: Optional[str] = None,
    ) -> Optional[str]:
        """Missing env var → default_if_unset; empty or whitespace-only → None."""
        raw = os.getenv(name)
        if raw is None:
            return default_if_unset
        stripped = raw.strip()
        return stripped if stripped else None

    def _bool_env(name: str, default: bool = False) -> bool:
        raw = (os.getenv(name) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
        if raw in ("0", "false", "no", "off"):
            return False
        return default

    return AppConfig(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        gigachat_auth_key=os.getenv("GIGACHAT_AUTH_KEY", ""),
        gigachat_scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        gigachat_model=os.getenv("GIGACHAT_MODEL", "GigaChat-Max"),
        gigachat_max_tokens=max_tokens,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
        proxy_api_key=os.getenv("PROXY_API_KEY", ""),
        proxy_openai_base_url=os.getenv(
            "PROXY_OPENAI_BASE_URL", "https://api.proxyapi.ru/openai/v1"
        ),
        proxy_image_model=os.getenv("PROXY_IMAGE_MODEL", "gpt-image-1"),
        image_provider=(os.getenv("IMAGE_PROVIDER", "proxy").strip().lower() or "proxy"),
        chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db"),
        rag_documents_dir=os.getenv("RAG_DOCUMENTS_DIR", "data/documents"),
        rag_top_k=_int_env("RAG_TOP_K", 3),
        rag_chunk_size=_int_env("RAG_CHUNK_SIZE", 1000),
        rag_chunk_overlap=_int_env("RAG_CHUNK_OVERLAP", 200),
        rag_answer_max_tokens=_int_env("RAG_ANSWER_MAX_TOKENS", 1500),
        openai_base_url=_optional_stripped_url("OPENAI_BASE_URL"),
        openai_embedding_model=os.getenv(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        ),
        rag_embedding_request_timeout=_float_env("RAG_EMBEDDING_REQUEST_TIMEOUT", 30.0),
        rag_retrieval_timeout=_int_env("RAG_RETRIEVAL_TIMEOUT", 60),
        admin_upload_max_mb=max(1, _int_env("ADMIN_UPLOAD_MAX_MB", 25)),
        rag_max_distance=_float_env("RAG_MAX_DISTANCE", 1.38),
        chroma_use_http=_bool_env("CHROMA_USE_HTTP", False),
        chroma_host=(os.getenv("CHROMA_HOST", "127.0.0.1").strip() or "127.0.0.1"),
        chroma_port=_int_env("CHROMA_PORT", 8000),
        database_url=_optional_stripped_url("DATABASE_URL"),
        rag_backend=(
            (os.getenv("RAG_BACKEND") or "").strip().lower() or "chroma"
        ),
        enable_hybrid_retrieval=_bool_env("ENABLE_HYBRID_RETRIEVAL", False),
        enable_ragas_evaluation=_bool_env("ENABLE_RAGAS_EVALUATION", False),
        rag_eval_dataset_path=(
            (os.getenv("RAG_EVAL_DATASET_PATH") or "").strip()
            or "evaluation/datasets/rag_smoke_dataset.json"
        ),
        rag_eval_output_dir=(
            (os.getenv("RAG_EVAL_OUTPUT_DIR") or "").strip() or "outputs/evaluation"
        ),
        cache_db_path=(
            (os.getenv("CACHE_DB_PATH") or "").strip()
            or "storage/cache/assistant_cache.sqlite3"
        ),
        enable_retrieval_cache=_bool_env("ENABLE_RETRIEVAL_CACHE", False),
        enable_answer_cache=_bool_env("ENABLE_ANSWER_CACHE", False),
        retrieval_cache_ttl_seconds=_int_env("RETRIEVAL_CACHE_TTL_SECONDS", 86_400),
        answer_cache_ttl_seconds=_int_env("ANSWER_CACHE_TTL_SECONDS", 86_400),
        faiss_index_dir=(
            (os.getenv("FAISS_INDEX_DIR") or "").strip() or "storage/faiss"
        ),
        weaviate_url=(os.getenv("WEAVIATE_URL") or "").strip(),
        weaviate_host=(os.getenv("WEAVIATE_HOST") or "weaviate").strip() or "weaviate",
        weaviate_http_port=_int_env("WEAVIATE_HTTP_PORT", 8080),
        weaviate_grpc_port=_int_env("WEAVIATE_GRPC_PORT", 50051),
        weaviate_class_name=(
            (os.getenv("WEAVIATE_CLASS_NAME") or "").strip() or "AssistantFlowChunk"
        ),
        asset_storage_backend=(
            os.getenv("ASSET_STORAGE_BACKEND", "filesystem").strip().lower()
            or "filesystem"
        ),
        asset_storage_dir=(
            os.getenv("ASSET_STORAGE_DIR", "/app/storage/assets").strip()
            or "/app/storage/assets"
        ),
        audio_enabled=_bool_env("AUDIO_ENABLED", True),
        stt_provider=(os.getenv("STT_PROVIDER", "disabled").strip().lower() or "disabled"),
        tts_provider=(os.getenv("TTS_PROVIDER", "disabled").strip().lower() or "disabled"),
        audio_storage_namespace=(
            os.getenv("AUDIO_STORAGE_NAMESPACE", "audio").strip().strip("/")
            or "audio"
        ),
        stt_model=(os.getenv("STT_MODEL", "whisper-1").strip() or "whisper-1"),
        audio_max_bytes=_int_env("AUDIO_MAX_BYTES", 20 * 1024 * 1024),
        tts_model=(os.getenv("TTS_MODEL", "tts-1").strip() or "tts-1"),
        tts_voice=(os.getenv("TTS_VOICE", "alloy").strip() or "alloy"),
        tts_output_format=(os.getenv("TTS_OUTPUT_FORMAT", "mp3").strip().lower() or "mp3"),
        tts_max_chars=_int_env("TTS_MAX_CHARS", 3000),
        audio_timeout_seconds=_int_env("AUDIO_TIMEOUT_SECONDS", 60),
        audio_max_retries=_int_env("AUDIO_MAX_RETRIES", 1),
        stt_cost_per_minute_usd=_float_env("STT_COST_PER_MINUTE_USD", 0.006),
        tts_cost_per_1m_chars_usd=_float_env("TTS_COST_PER_1M_CHARS_USD", 15.0),
        telegram_pg_conversation_memory=_bool_env("TELEGRAM_PG_CONVERSATION_MEMORY", True),
        telegram_memory_max_turn_pairs=_int_env("TELEGRAM_MEMORY_MAX_TURN_PAIRS", 6),
        telegram_memory_max_llm_messages=_int_env("TELEGRAM_MEMORY_MAX_LLM_MESSAGES", 24),
        rag_conversation_history_max_chars=_int_env(
            "RAG_CONVERSATION_HISTORY_MAX_CHARS", 12_000
        ),
        chat_session_idle_timeout_seconds=_int_env("CHAT_SESSION_IDLE_TIMEOUT_SECONDS", 0),
    )
