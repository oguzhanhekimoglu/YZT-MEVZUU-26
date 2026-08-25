import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { FinalOutput } from "../../types";
import { formatFinalOutputJson } from "./json-output";
import styles from "./JsonOutputDialog.module.css";
import { lockOverlayEnvironment } from "../../components/ui/overlay-environment";

export function JsonOutputDialog({ output, onClose }: { output: FinalOutput; onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const unlockOverlay = lockOverlayEnvironment();
    closeRef.current?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>("button")];
      const first = focusable[0]; const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); unlockOverlay(); previous?.focus(); };
  }, [onClose]);
  return createPortal(<div className={styles.backdrop}><div ref={dialogRef} className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="json-title"><header><div><h2 id="json-title">Canonical JSON Çıktısı</h2><p>Canonical nihai çıktının ham JSON gösterimi.</p></div><button ref={closeRef} type="button" onClick={onClose} aria-label="JSON penceresini kapat">×</button></header><pre>{formatFinalOutputJson(output)}</pre></div></div>, document.body);
}
