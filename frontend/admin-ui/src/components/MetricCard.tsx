import type { ReactNode } from "react";

interface MetricCardProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export function MetricCard({ title, children, className = "" }: MetricCardProps) {
  return (
    <section className={`card ${className}`.trim()}>
      <h2 className="card__title">{title}</h2>
      <div className="card__body">{children}</div>
    </section>
  );
}
