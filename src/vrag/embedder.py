import torch
import numpy as np
from PIL import Image
from transformers import AutoProcessor, AutoModel
import logging
from src.config import SIGLIP_MODEL_NAME, VRAG_DEVICE

log = logging.getLogger(__name__)

class VisualEmbedder:
    """
    SigLIP (veya CLIP) tabanlı görsel vektör çıkarıcı.
    Verilen OpenCV (BGR) veya PIL formatındaki görüntüleri Qdrant'ta saklanacak
    veya aranacak vektörlere (embedding) dönüştürür.
    """
    def __init__(self):
        log.info(f"[VRAG] Embedder yükleniyor: {SIGLIP_MODEL_NAME} ({VRAG_DEVICE})")
        self.device = VRAG_DEVICE
        
        try:
            self.processor = AutoProcessor.from_pretrained(SIGLIP_MODEL_NAME)
            self.model = AutoModel.from_pretrained(SIGLIP_MODEL_NAME).to(self.device)
            self.model.eval()
            self.vector_size = self.model.config.vision_config.hidden_size
            log.info(f"[VRAG] Embedder hazır! Vektör boyutu: {self.vector_size}")
        except Exception as e:
            log.error(f"[VRAG] Embedder yükleme hatası: {e}")
            raise

    def embed_image(self, image) -> np.ndarray:
        """
        Görüntüden vektör çıkarır.
        :param image: numpy array (BGR) veya PIL Image
        :return: 1D numpy array (normalize edilmiş embedding)
        """
        # Numpy (OpenCV BGR) ise PIL RGB'ye çevir
        if isinstance(image, np.ndarray):
            import cv2
            image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            
        with torch.no_grad():
            inputs = self.processor(images=image, return_tensors="pt").to(self.device)
            
            # BUG-FIX: `vision_model(**inputs)` doğrudan vision transformer'ın ham (projeksiyon
            # edilmemiş) çıktılarını veriyordu. SigLIP'in gerçek vektör uzayına (F-15 ile F-16'yı
            # birbirinden ayıran kontrastif uzay) ulaşmak için görüntülerin `visual_projection`
            # katmanından geçmesi ŞARTTIR. Bu yüzden `get_image_features` kullanmalıyız.
            if hasattr(self.model, "get_image_features"):
                emb = self.model.get_image_features(**inputs)
            else:
                emb = self.model.vision_model(**inputs)
                if hasattr(emb, "pooler_output"):
                    emb = emb.pooler_output
                elif hasattr(emb, "image_embeds"):
                    emb = emb.image_embeds
                elif not isinstance(emb, torch.Tensor):
                    emb = emb[0]
            
            if not isinstance(emb, torch.Tensor):
                if hasattr(emb, 'pooler_output') and emb.pooler_output is not None:
                    emb = emb.pooler_output
                elif hasattr(emb, 'image_embeds') and emb.image_embeds is not None:
                    emb = emb.image_embeds
                elif hasattr(emb, 'last_hidden_state') and emb.last_hidden_state is not None:
                    # Fallback
                    emb = emb.last_hidden_state
                else:
                    emb = emb[0]
                    
            # Eğer hala tensor değilse (çok nadir), hata vermesin
            if not isinstance(emb, torch.Tensor):
                emb = torch.tensor(emb)
                
            # Eğer boyut (batch, seq, dim) ise, sadece pool edilmiş kısmı veya ilk token'i al
            if emb.ndim == 3:
                # Genelde 0. index CLS token veya global average pool'dur
                emb = emb[:, 0, :]
                
            # CPU'ya al ve numpy yap
            emb = emb.cpu().numpy()[0]
            
            # L2 Normalizasyon (Cosine similarity için şart)
            emb = emb / np.linalg.norm(emb)
            return emb
