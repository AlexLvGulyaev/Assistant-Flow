"""
Контекст безопасности retrieval (P6.7): роль, источники, scope, metadata/tags.

Без интеграции в auth/UI. Значение по умолчанию для вызовов без контекста — permissive
(совпадает с поведением до P6.7).
"""

from __future__ import annotations

from dataclasses import dataclass

# Идентификаторы ролей для политик и телеметрии (не production RBAC).
ROLE_GUEST = "guest"
ROLE_EMPLOYEE = "employee"
ROLE_ADMIN = "admin"


@dataclass(frozen=True)
class RetrievalSecurityContext:
    """
    Минимальный контракт retrieval-side security.

    - ``allowed_sources is None`` — любые источники (наследуемое поведение).
    - ``allowed_sources == frozenset()`` — явный запрет всех источников (пустой retrieval).
    - ``metadata_filters`` — пары (ключ, значение) для равенства в Chroma ``$and`` / post-filter
      (заготовка под ``source`` / ``document_type`` / ``visibility`` и др.).
    - ``required_tags`` — чанк должен содержать все перечисленные теги (post-filter;
      сложные запросы по тегам в Chroma where намеренно не дублируем).
    """

    role: str = ROLE_GUEST
    allowed_sources: frozenset[str] | None = None
    retrieval_scope: str = "unrestricted"
    metadata_filters: tuple[tuple[str, str], ...] = ()
    required_tags: frozenset[str] = frozenset()
    #: Допустимые значения ``visibility`` / ``document_visibility``; ``None`` — без фильтра.
    allowed_visibility: frozenset[str] | None = None

    @classmethod
    def permissive_default(cls) -> RetrievalSecurityContext:
        """Политика по умолчанию: без ограничений (backward-compatible)."""
        return cls(
            role=ROLE_ADMIN,
            allowed_sources=None,
            retrieval_scope="unrestricted",
            metadata_filters=(),
            required_tags=frozenset(),
            allowed_visibility=None,
        )

    def is_fully_unrestricted(self) -> bool:
        return (
            self.allowed_sources is None
            and self.retrieval_scope == "unrestricted"
            and not self.metadata_filters
            and not self.required_tags
            and self.allowed_visibility is None
        )

    def restricts_vector_query(self) -> bool:
        """Нужен ли непустой ``where`` в Chroma (источники с $in / простые metadata).

        ``allowed_sources == frozenset()`` не требует where: недопустимый ``$in: []``.
        """
        if self.allowed_sources is not None and len(self.allowed_sources) > 0:
            return True
        if self.allowed_visibility is not None and len(self.allowed_visibility) > 0:
            return True
        return any(str(k).strip() for k, _ in self.metadata_filters)

    def to_cache_fingerprint_extra(self) -> str | None:
        """Сегмент для retrieval cache fingerprint; None — не добавлять в ключ."""
        if self.is_fully_unrestricted():
            return None
        parts: list[str] = [
            f"role={self.role}",
            f"scope={self.retrieval_scope}",
        ]
        if self.allowed_sources is not None:
            parts.append("sources=" + ",".join(sorted(self.allowed_sources)))
        else:
            parts.append("sources=*")
        if self.metadata_filters:
            parts.append(
                "meta="
                + ",".join(f"{k}={v}" for k, v in sorted(self.metadata_filters))
            )
        if self.required_tags:
            parts.append("req_tags=" + ",".join(sorted(self.required_tags)))
        if self.allowed_visibility is not None:
            parts.append("vis=" + ",".join(sorted(self.allowed_visibility)))
        return "|".join(parts)
