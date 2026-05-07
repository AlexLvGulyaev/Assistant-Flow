import type { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}

export function SectionCard({
  title,
  description,
  children,
  className = "",
}: SectionCardProps) {
  return (
    <section className={`section-card card ${className}`.trim()}>
      <header className="section-card__header">
        <h2 className="card__title">{title}</h2>
        {description ? (
          <p className="section-card__desc muted">{description}</p>
        ) : null}
      </header>
      <div className="card__body">{children}</div>
    </section>
  );
}
