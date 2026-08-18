import json
import logging
from pathlib import Path

import numpy as np
from src.vrag.embedder import VisualEmbedder
from src.vrag.db import QdrantManager
from src.config import VRAG_MIN_SCORE

log = logging.getLogger(__name__)

VERI_DIZINI = Path(__file__).resolve().parent.parent.parent / "data" / "referans"


def _metadata_onbellegi_olustur() -> dict[str, dict]:
    """model adı → {ulke, uretici, rol} eşlemesi (data/referans/**/metadata.json'dan).

    BUG-FIX: ingest.py, indeksleme sırasında Qdrant payload'ına yalnızca
    model/class/source_file/variation yazıyordu — ulke/uretici/rol hiç
    depolanmıyordu (kaynak metadata.json'da var olsa bile). Bu, arama
    sonuçlarının hep "Bilinmiyor" dönmesine yol açıyordu. Saatler süren
    yeniden indeksleme yerine, arama anında model adına göre metadata'yı
    diskten okuyup zenginleştiriyoruz.
    """
    onbellek: dict[str, dict] = {}
    if not VERI_DIZINI.is_dir():
        return onbellek
    for meta_path in VERI_DIZINI.rglob("metadata.json"):
        try:
            veri = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        model = veri.get("model")
        if model:
            onbellek[model] = {
                "ulke": veri.get("ulke", "Bilinmiyor"),
                "uretici": veri.get("uretici", "Bilinmiyor"),
                "rol": veri.get("rol", "Bilinmiyor"),
            }
    return onbellek


class VRAGEngine:
    def __init__(self):
        log.info("[VRAG] VRAG Engine başlatılıyor...")
        self.embedder = VisualEmbedder()
        self.db = QdrantManager(vector_size=self.embedder.vector_size)
        self._metadata_onbellegi = _metadata_onbellegi_olustur()
        log.info(f"[VRAG] {len(self._metadata_onbellegi)} model için metadata önbelleğe alındı.")

    def search_similar_vehicle(self, image: np.ndarray, top_k: int = 2) -> list:
        """
        Hedef kameradan gelen kırpılmış (crop) görüntüyü VRAG DB'de arar
        ve eşleşmeleri döndürür.
        """
        try:
            emb = self.embedder.embed_image(image)
            results = self.db.search(query_vector=emb, limit=top_k)

            matches = []
            for hit in results:
                if hit.score >= VRAG_MIN_SCORE:
                    model = hit.payload.get("model", "Bilinmiyor")
                    meta = self._metadata_onbellegi.get(model, {})
                    matches.append({
                        "model": model,
                        "class": hit.payload.get("class", "Bilinmiyor"),
                        "score": hit.score,
                        "ulke": meta.get("ulke", "Bilinmiyor"),
                        "uretici": meta.get("uretici", "Bilinmiyor"),
                        "rol": meta.get("rol", "Bilinmiyor"),
                    })
            return matches
        except Exception as e:
            log.error(f"[VRAG] Arama sırasında hata oluştu: {e}")
            return []
