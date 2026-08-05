"""Embedding (gömme) — görüntü -> vektör (tek encoder: SigLIP2-so400m).

Encoder bir kez yüklenir ve süreç boyunca bellekte tutulur (singleton). Özellik
çıkarma yöntemi otomatik seçilir: SigLIP/CLIP ailesinde `get_image_features`,
DINOv2/ViT'te `pooler_output`. Vektör boyutu ilk çıkarımda belirlenir.
"""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image

from . import config


class Gomleyici:
    """SigLIP2 görüntü encoder'ı; L2-normalize vektörler üretir."""

    def __init__(self, model_adi: str | None = None, cihaz: str = config.CIHAZ):
        from transformers import AutoImageProcessor, AutoModel

        model_adi = model_adi or config.ENCODER_MODELI
        self.cihaz = cihaz
        self.islemci = AutoImageProcessor.from_pretrained(model_adi, use_fast=True)
        self.model = AutoModel.from_pretrained(model_adi).to(cihaz).eval()
        self._get_feat = hasattr(self.model, "get_image_features")
        # Kukla bir görselle vektör boyutunu belirle.
        self._boyut = int(self.gomle([Image.new("RGB", (224, 224))]).shape[1])

    @property
    def boyut(self) -> int:
        return self._boyut

    def _vektor(self, girdiler) -> torch.Tensor:
        if self._get_feat:                       # SigLIP / CLIP ailesi
            return self.model.get_image_features(**girdiler)
        cikti = self.model(**girdiler)
        havuz = getattr(cikti, "pooler_output", None)
        if havuz is not None:                    # DINOv2 / ViT
            return havuz
        return cikti.last_hidden_state.mean(dim=1)

    @torch.no_grad()
    def gomle(self, goruntuler: list[Image.Image]) -> np.ndarray:
        """Görüntü listesini (N, boyut) float32, L2-normalize diziye çevirir."""
        if not goruntuler:
            return np.empty((0, getattr(self, "_boyut", 0) or 0), dtype=np.float32)

        parcalar: list[np.ndarray] = []
        for bas in range(0, len(goruntuler), config.TOPLU_BOYUT):
            grup = [g.convert("RGB") for g in goruntuler[bas:bas + config.TOPLU_BOYUT]]
            girdiler = self.islemci(images=grup, return_tensors="pt").to(self.cihaz)
            vektor = torch.nn.functional.normalize(self._vektor(girdiler), p=2, dim=-1)
            parcalar.append(vektor.cpu().numpy().astype(np.float32))

        return np.concatenate(parcalar, axis=0)


# Süreç boyunca tek yerleşik encoder.
_gomleyici: Gomleyici | None = None


def gomleyici_al() -> Gomleyici:
    """Yerleşik encoder örneğini döndürür; ilk çağrıda yükler."""
    global _gomleyici
    if _gomleyici is None:
        _gomleyici = Gomleyici()
    return _gomleyici
