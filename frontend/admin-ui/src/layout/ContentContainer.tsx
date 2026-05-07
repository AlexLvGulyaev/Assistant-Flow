import type { ReactNode } from "react";

interface ContentContainerProps {
  children: ReactNode;
}

/** Scrollable main column — shell keeps sidebar/topbar fixed. */
export function ContentContainer({ children }: ContentContainerProps) {
  return <div className="admin-shell__content">{children}</div>;
}
