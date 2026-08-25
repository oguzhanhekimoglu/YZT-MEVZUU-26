import type { TargetAnalysis } from "../../types";
import styles from "./AnalysisScopeSelector.module.css";

interface Props {
  scope: "video" | "target";
  targetId?: number;
  targets: TargetAnalysis[];
  onVideo: () => void;
  onTarget: (id: number) => void;
}

export function AnalysisScopeSelector({ scope, targetId, targets, onVideo, onTarget }: Props) {
  return (
    <div className={styles.selector} role="tablist" aria-label="Analiz kapsamı">
      <button type="button" role="tab" aria-selected={scope === "video"} onClick={onVideo}>Video Geneli</button>
      {targets.map((target) => <button key={target.id} type="button" role="tab" aria-selected={scope === "target" && target.id === targetId} onClick={() => onTarget(target.id)}>Hedef #{target.id}</button>)}
    </div>
  );
}
