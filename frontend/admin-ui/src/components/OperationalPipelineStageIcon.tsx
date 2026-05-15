import type { AfPipelineStageVariant } from "../utils/operationalConsoleUi";

type Props = {
  variant: AfPipelineStageVariant;
  className?: string;
};

export function OperationalPipelineStageIcon({ variant, className = "" }: Props) {
  return (
    <span
      className={`af-pipeline-stage-icon af-pipeline-stage-icon--${variant}${
        className ? ` ${className}` : ""
      }`}
      aria-hidden
    />
  );
}
