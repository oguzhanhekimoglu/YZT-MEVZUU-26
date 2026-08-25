import type { AircraftCandidate } from "../../types";
import { percent } from "./analysis-utils";
import styles from "./CandidateList.module.css";

export function uniqueCandidates(candidates: AircraftCandidate[]): AircraftCandidate[] {
  const byModel = new Map<string, AircraftCandidate>();
  for (const candidate of candidates) {
    if (!candidate.model.trim() || !Number.isFinite(candidate.score)) continue;
    const existing = byModel.get(candidate.model);
    if (!existing || candidate.score > existing.score) byModel.set(candidate.model, candidate);
  }
  return [...byModel.values()].sort((a, b) => b.score - a.score).slice(0, 5);
}

export function CandidateList({ candidates }: { candidates: AircraftCandidate[] }) {
  const unique = uniqueCandidates(candidates);
  if (!unique.length) return <p className={styles.empty}>Benzer aday henüz mevcut değil.</p>;
  return <ol className={styles.list}>{unique.map((candidate) => { const score = Math.min(1, Math.max(0, candidate.score)); return <li key={candidate.model}><div><span>{candidate.model}</span><strong>{percent(candidate.score)}</strong></div><span className={styles.track}><span style={{ width: `${score * 100}%` }} /></span></li>; })}</ol>;
}
