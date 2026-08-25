import type { AnalysisStep, FinalOutput, TargetAnalysis } from "../../types";
import { AnalysisStepItem } from "./AnalysisStepItem";
import { DecisionChainPanel } from "./DecisionChainPanel";

export function AnalysisStepList({ steps, openStepId, requestedStepId, target, output, sessionId, onToggle }: { steps: AnalysisStep[]; openStepId?: AnalysisStep["id"]; requestedStepId?: AnalysisStep["id"]; target?: TargetAnalysis; output: FinalOutput; sessionId: string; onToggle: (id: AnalysisStep["id"]) => void }) {
  return <div>{steps.map((step) => {
    if (target && step.id === "vrag") return <DecisionChainPanel key={`decision-chain-${target.id}`} target={target} requestedStepId={requestedStepId} />;
    if (target && (step.id === "vlm" || step.id === "llm")) return null;
    return <AnalysisStepItem key={step.id} step={step} open={step.id === openStepId} target={target} output={output} sessionId={sessionId} onToggle={() => onToggle(step.id)} />;
  })}</div>;
}
