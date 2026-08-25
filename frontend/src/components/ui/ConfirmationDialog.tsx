import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import styles from "./ConfirmationDialog.module.css";
import { lockOverlayEnvironment } from "./overlay-environment";

interface Props { title: string; description: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; }

export function ConfirmationDialog({ title, description, confirmLabel, onConfirm, onCancel }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const unlockOverlay = lockOverlayEnvironment();
    cancelRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const buttons = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button"));
      const first = buttons[0];
      const last = buttons.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); unlockOverlay(); previous?.focus(); };
  }, [onCancel]);

  return createPortal(
    <div className={styles.backdrop} onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}>
      <div ref={dialogRef} className={styles.dialog} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-description">
        <h2 id="confirm-title">{title}</h2>
        <p id="confirm-description">{description}</p>
        <div className={styles.actions}>
          <button ref={cancelRef} type="button" onClick={onCancel}>Vazgeç</button>
          <button type="button" className={styles.danger} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
