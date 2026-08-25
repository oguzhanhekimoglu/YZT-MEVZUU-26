import { createContext, type PropsWithChildren, useCallback, useContext, useMemo, useState } from "react";
import type { AnalysisStep } from "../../types";

export interface AnalysisDrawerRequest {
  scope: "video" | "target";
  targetId?: number;
  stepId?: AnalysisStep["id"];
}

interface AnalysisDrawerState {
  isOpen: boolean;
  request?: AnalysisDrawerRequest;
}

interface AnalysisDrawerController extends AnalysisDrawerState {
  openAnalysis: (request: AnalysisDrawerRequest) => void;
  closeAnalysis: () => void;
}

const AnalysisDrawerContext = createContext<AnalysisDrawerController | null>(null);

export function AnalysisDrawerProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<AnalysisDrawerState>({ isOpen: false });
  const openAnalysis = useCallback((request: AnalysisDrawerRequest) => setState({ isOpen: true, request }), []);
  const closeAnalysis = useCallback(() => setState((current) => ({ ...current, isOpen: false })), []);
  const value = useMemo(() => ({ ...state, openAnalysis, closeAnalysis }), [state, openAnalysis, closeAnalysis]);
  return (
    <AnalysisDrawerContext.Provider value={value}>
      {children}
    </AnalysisDrawerContext.Provider>
  );
}

export function useAnalysisDrawer(): AnalysisDrawerController {
  const controller = useContext(AnalysisDrawerContext);
  if (!controller) throw new Error("AnalysisDrawerProvider bulunamadı.");
  return controller;
}
