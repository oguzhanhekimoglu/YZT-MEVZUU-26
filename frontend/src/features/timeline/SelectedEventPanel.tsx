import type { OperatorDataSource } from "../../services/contracts";
import type { OperatorSession, TimelineEvent } from "../../types";
import { useAnalysisDrawer } from "../analysis-process/analysis-drawer-context";
import { SelectedEventDetail } from "./SelectedEventDetail";
import { Icon } from "../../components/ui/Icon";
import styles from "./SelectedEventPanel.module.css";

export function SelectedEventPanel({
  event,
  session,
  dataSource,
  onClose,
}: {
  event?: TimelineEvent;
  session: OperatorSession;
  dataSource: OperatorDataSource;
  onClose?: () => void;
}) {
  const { openAnalysis } = useAnalysisDrawer();
  if (!event) return null;

  return (
    <section className={styles.panel} aria-label="Seçili olay ayrıntısı">
      <header className={styles.header}>
        <span className={styles.eyebrow}>SEÇİLİ OLAY</span>
        {onClose && (
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Seçili olayı kapat"
            title="Kapat (Esc)"
          >
            <Icon name="close" size={13} />
          </button>
        )}
      </header>
      <SelectedEventDetail
        event={event}
        targets={session.targets.filter((target) => target.id !== -1)}
        onSelectTarget={(id) => void dataSource.selectTarget(id)}
        onOpenAnalysis={openAnalysis}
      />
    </section>
  );
}
