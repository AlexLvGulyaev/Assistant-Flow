import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  chunkPreviewText,
  relevanceLabel,
  type SharedRetrievalChunk,
} from "../utils/retrievalChunks";

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function ChunkFullTextModal({
  chunk,
  displayIndex,
  relevance,
  backendTitle,
  onClose,
}: {
  chunk: SharedRetrievalChunk;
  displayIndex: number;
  relevance: string;
  backendTitle: string;
  onClose: () => void;
}) {
  const full = chunk.fullText?.trim() || "Текст чанка не передан в логах.";
  return (
    <div className="rag-chunk-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="rag-chunk-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ops-chunk-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rag-chunk-modal__head">
          <h2 id="ops-chunk-modal-title" className="rag-chunk-modal__title">
            Полный текст чанка
          </h2>
          <button
            type="button"
            className="rag-chunk-modal__close"
            onClick={onClose}
            aria-label="Закрыть"
          >
            ×
          </button>
        </div>
        <dl className="kv rag-chunk-modal__meta modality-ops-panel__kv">
          <OpsRow label="Backend" value={<span className="mono">{backendTitle}</span>} />
          <OpsRow
            label="Файл"
            value={
              <span className="mono break-all">{chunk.source || "неизвестный файл"}</span>
            }
          />
          <OpsRow label="Индекс чанка" value={<span className="mono">#{displayIndex}</span>} />
          <OpsRow
            label="distance"
            value={
              chunk.distance != null && Number.isFinite(chunk.distance) ? (
                <span className="mono">{chunk.distance.toFixed(4)}</span>
              ) : (
                "—"
              )
            }
          />
          <OpsRow label="Релевантность" value={relevance} />
        </dl>
        <pre className="mono rag-chunk-modal__body">{full}</pre>
        <div className="rag-chunk-modal__foot">
          <button type="button" className="rag-chunk-modal__done" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}

function RetrievalChunkCard({
  chunk,
  displayIndex,
  relevanceThreshold,
  backendTitle,
  onShowFull,
}: {
  chunk: SharedRetrievalChunk;
  displayIndex: number;
  relevanceThreshold: number | null;
  backendTitle: string;
  onShowFull: () => void;
}) {
  const rel = relevanceLabel(chunk, relevanceThreshold);
  const score =
    chunk.distance != null && Number.isFinite(chunk.distance)
      ? chunk.distance.toFixed(4)
      : "—";
  return (
    <article className="rag-chunk-card">
      <header className="rag-chunk-card__header">
        <div className="rag-chunk-card__meta-row">
          <div className="rag-chunk-card__meta-left mono">
            <span className="rag-chunk-card__filename" title={chunk.source}>
              {chunk.source || "неизвестный файл"}
            </span>
            <span className="rag-chunk-card__chunk-no">#{displayIndex}</span>
            <span className="rag-chunk-card__distance" title="Score / distance">
              {score}
            </span>
            <span className="rag-chunk-card__backend-inline">
              backend: <span className="rag-chunk-card__backend-name">{backendTitle}</span>
            </span>
          </div>
          <button type="button" className="rag-chunk-card__fulltext-cta" onClick={onShowFull}>
            показать полный текст
          </button>
          <div className="rag-chunk-card__meta-right">
            <span className="rag-chunk-card__relevance">{rel}</span>
          </div>
        </div>
      </header>
      <div className="rag-chunk-card__body">
        <p className="rag-chunk-card__preview mono">{chunkPreviewText(chunk)}</p>
      </div>
    </article>
  );
}

export function OperationalRetrievalChunksSection({
  title = "Найденные чанки",
  chunks,
  relevanceThreshold = null,
  getBackendTitle,
  emptyMessage = "Чанки не переданы в логах или retrieval пустой.",
  dedupeNote,
}: {
  title?: string;
  chunks: SharedRetrievalChunk[];
  relevanceThreshold?: number | null;
  getBackendTitle: (chunk: SharedRetrievalChunk, index: number) => string;
  emptyMessage?: string;
  dedupeNote?: ReactNode;
}) {
  const [modal, setModal] = useState<{
    chunk: SharedRetrievalChunk;
    displayIndex: number;
    relevance: string;
    backendTitle: string;
  } | null>(null);

  return (
    <section className="rag-chunks-primary" aria-label={title}>
      <h3 className="logs-timeline-heading rag-chunks-primary__title">{title}</h3>
      {dedupeNote}
      {chunks.length === 0 ? (
        <div className="panel panel--muted rag-chunks-empty">{emptyMessage}</div>
      ) : (
        chunks.map((chunk, i) => {
          const idx = chunk.chunkIndex ?? i;
          const backendTitle = getBackendTitle(chunk, i);
          return (
            <RetrievalChunkCard
              key={`${chunk.source}-${idx}-${i}`}
              chunk={chunk}
              displayIndex={idx}
              relevanceThreshold={relevanceThreshold ?? null}
              backendTitle={backendTitle}
              onShowFull={() =>
                setModal({
                  chunk,
                  displayIndex: idx,
                  relevance: relevanceLabel(chunk, relevanceThreshold ?? null),
                  backendTitle,
                })
              }
            />
          );
        })
      )}
      {typeof document !== "undefined" && modal
        ? createPortal(
            <ChunkFullTextModal
              chunk={modal.chunk}
              displayIndex={modal.displayIndex}
              relevance={modal.relevance}
              backendTitle={modal.backendTitle}
              onClose={() => setModal(null)}
            />,
            document.body
          )
        : null}
    </section>
  );
}
