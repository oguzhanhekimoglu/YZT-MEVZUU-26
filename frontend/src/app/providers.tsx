import { createContext, type PropsWithChildren, useContext } from "react";
import { operatorDataSource } from "../services/data-source";
import type { OperatorDataSource } from "../services/contracts";
import { AnalysisDrawerProvider } from "../features/analysis-process/analysis-drawer-context";
import { ThemeProvider } from "./theme";

const OperatorDataSourceContext = createContext<OperatorDataSource | null>(null);

interface AppProvidersProps extends PropsWithChildren {
  dataSource?: OperatorDataSource;
}

export function AppProviders({ children, dataSource = operatorDataSource }: AppProvidersProps) {
  return (
    <ThemeProvider>
      <OperatorDataSourceContext.Provider value={dataSource}>
        <AnalysisDrawerProvider>{children}</AnalysisDrawerProvider>
      </OperatorDataSourceContext.Provider>
    </ThemeProvider>
  );
}

export function useOperatorDataSource(): OperatorDataSource {
  const dataSource = useContext(OperatorDataSourceContext);

  if (!dataSource) {
    throw new Error("OperatorDataSource sağlayıcısı bulunamadı.");
  }

  return dataSource;
}
