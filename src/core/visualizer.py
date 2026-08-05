import cv2
import numpy as np
import logging
import src.config as cfg
from src.config import (
    ARENA_POLYGON, SAVE_VIDEO, OUTPUT_DIR
)

log = logging.getLogger(__name__)

class PipelineVisualizer:
    def __init__(self, source_fps: float):
        self._source_fps = source_fps
        self._video_writer = None
        self._window_created = False

    def draw_and_save(self, frame, targets, raw_dets, fps, total_ms, fw, fh, t_slicer, t_tracker, suspended_count):
        vis = frame.copy()

        if ARENA_POLYGON:
            pts = np.array(
                [(int(px*fw), int(py*fh)) for px, py in ARENA_POLYGON],
                dtype=np.int32
            )
            cv2.polylines(vis, [pts], isClosed=True, color=(0, 255, 128), thickness=2)
            cv2.putText(vis, "ARENA", (pts[0][0], pts[0][1]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,128), 1, cv2.LINE_AA)

        for d in raw_dets:
            cv2.circle(vis, (int(d.cx), int(d.cy)), 3, (180, 180, 180), -1)

        for rank, t in enumerate(targets):
            x1, y1, x2, y2 = t.bbox_xyxy
            
            cls_type = getattr(t, "classified_type", "UÇAK / İHA")
            cls_conf = getattr(t, "type_confidence", t.confidence)
            is_bird  = "KUŞ" in cls_type.upper() or "BIRD" in cls_type.upper()
            
            color = (0, 220, 150) if is_bird else (0, 80, 255)
            badge = f"[KUŞ %{int(cls_conf*100)}]" if is_bird else f"[UÇAK/İHA %{int(cls_conf*100)}]"

            thick = 2 if t.in_arena else 1
            if not t.in_arena:
                color = tuple(int(c * 0.4) for c in color)
                
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, thick)

            heading = getattr(t, 'visual_heading', None)
            
            if heading is not None:
                cx, cy = (x1+x2)//2, (y1+y2)//2
                arrow_len = max(40.0, min(x2-x1, y2-y1) * 0.8)
                
                hx, hy = heading
                ax = int(cx + hx * arrow_len)
                ay = int(cy + hy * arrow_len)
                
                cv2.arrowedLine(vis, (cx, cy), (ax, ay),
                                color, 2, tipLength=0.35)

            rank_label = f"#{rank+1}"
            cv2.putText(vis, rank_label, (x2+3, y1+14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

            arena_tag = "" if t.in_arena else " [ARENA DISI]"
            label = (
                f"{badge} ID:{t.track_id} | "
                f"conf:{t.confidence:.2f} | "
                f"spd:{t.speed_px_s:.0f}px/s | "
                f"zz:{t.zigzag_score:.2f} | "
                f"thr:{t.threat_score:.2f}{arena_tag}"
            )
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.rectangle(vis, (x1, y1-lh-8), (x1+lw+4, y1), color, -1)
            cv2.putText(vis, label, (x1+2, y1-4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1, cv2.LINE_AA)

            if t.vlm_ready and len(t.best_crops) > 0:
                cv2.putText(vis, "[FOTOGRAF CEKILDI]", (x1, y2+16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,0), 1, cv2.LINE_AA)
            elif not t.in_arena:
                cv2.putText(vis, "[ARENA DISI]", (x1, y2+16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 100, 255), 1, cv2.LINE_AA)

            if getattr(t, "vrag_matches", None):
                top_match = t.vrag_matches[0]
                vrag_str = f"VRAG: {top_match['model']} (%{int(top_match['score']*100)})"
                cv2.putText(vis, vrag_str, (x1, y2+32),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1, cv2.LINE_AA)

        # deque slice desteklemez → list() ile son N eleman alınır
        _sl = list(t_slicer)[-10:]
        _tr = list(t_tracker)[-10:]
        s_ms  = (sum(_sl) / max(len(_sl), 1)) * 1000
        tr_ms = (sum(_tr) / max(len(_tr), 1)) * 1000
        hud = [
            f"FPS: {fps:.1f}  ({total_ms:.0f}ms/frame)",
            f"Slicer: {s_ms:.0f}ms | Tracker: {tr_ms:.0f}ms",
            f"Ham: {len(raw_dets)} | Onay: {len(targets)} | Askı: {suspended_count}",
            f"VLM Hazir: {sum(1 for t in targets if t.vlm_ready)}",
        ]
        for i, line in enumerate(hud):
            cv2.putText(vis, line, (10, 28+i*24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0,255,0), 2, cv2.LINE_AA)

        if cfg.SHOW_WINDOW:
            if not self._window_created:
                h, w = vis.shape[:2]
                cv2.namedWindow("TeknoFest Pipeline v3", cv2.WINDOW_NORMAL)
                cv2.resizeWindow("TeknoFest Pipeline v3", w, h)
                self._window_created = True
            cv2.imshow("TeknoFest Pipeline v3", vis)
            cv2.waitKey(1)

        if SAVE_VIDEO:
            if self._video_writer is None:
                h, w = vis.shape[:2]
                out_path = str(OUTPUT_DIR / "output.avi")
                self._video_writer = cv2.VideoWriter(
                    out_path, cv2.VideoWriter_fourcc(*"XVID"), self._source_fps, (w, h))
                log.info(f"Video: {out_path} @ {self._source_fps:.1f} FPS")
            self._video_writer.write(vis)
            
        return vis

    def release(self):
        if self._video_writer:
            self._video_writer.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
