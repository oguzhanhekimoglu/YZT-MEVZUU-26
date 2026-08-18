import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from src.config import VRAG_DB_PATH, VRAG_COLLECTION_NAME
import uuid

log = logging.getLogger(__name__)

class QdrantManager:
    def __init__(self, vector_size: int):
        log.info(f"[VRAG] Qdrant veritabanına bağlanılıyor: {VRAG_DB_PATH}")
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="qdrant_client")
            self.client = QdrantClient(path=str(VRAG_DB_PATH))
        self.collection_name = VRAG_COLLECTION_NAME
        
        self._init_collection(vector_size)

    def _init_collection(self, vector_size: int):
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            log.info(f"[VRAG] Yeni koleksiyon oluşturuluyor: {self.collection_name} (Boyut: {vector_size})")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        else:
            log.info(f"[VRAG] Koleksiyon mevcut: {self.collection_name}")

    def upsert_image(self, embedding: list, payload: dict):
        """
        Tek bir görüntünün vektörünü ve metadatasını kaydeder.
        """
        point_id = str(uuid.uuid4())
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload=payload
                )
            ]
        )
        return point_id

    def indekslenmis_dosyalari_al(self) -> set[tuple[str, str]]:
        """
        Zaten indekslenmiş (model, source_file) çiftlerini döndürür.

        Neden var: upsert_image her çağrıda rastgele bir UUID kullanıyor —
        aynı klasörü ikinci kez ingest edersen aynı görseller tekrar
        eklenip veritabanını (ve arama sonuçlarını) şişiriyordu. Bu metod,
        ingest.py'nin "zaten var, atla" kararı verebilmesini sağlıyor.
        """
        gorulen: set[tuple[str, str]] = set()
        sonraki_sayfa = None
        while True:
            noktalar, sonraki_sayfa = self.client.scroll(
                collection_name=self.collection_name,
                with_payload=True,
                with_vectors=False,
                limit=1000,
                offset=sonraki_sayfa,
            )
            for nokta in noktalar:
                model = nokta.payload.get("model")
                kaynak = nokta.payload.get("source_file")
                if model and kaynak:
                    gorulen.add((model, kaynak))
            if sonraki_sayfa is None:
                break
        return gorulen

    def dosya_sil(self, model: str, source_file: str) -> None:
        """
        Belirli bir (model, source_file) çiftine ait TÜM varyasyon noktalarını
        koleksiyondan siler.

        Neden var: "data/referans/" klasöründen bir model/görsel kaldırıldığında
        (ör. bir kategorinin tamamen silinmesi), indeksteki eski vektörler
        otomatik silinmiyordu — VRAG artık diskte olmayan bir modeli hâlâ
        "tanıyabiliyordu". ingest.py bunu, disk ile indeksi karşılaştırıp
        yalnızca diskte kalmayan dosyalar için çağırıyor.
        """
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(key="model", match=MatchValue(value=model)),
                    FieldCondition(key="source_file", match=MatchValue(value=source_file)),
                ]
            ),
        )

    def search(self, query_vector: list, limit: int = 3):
        """
        Verilen vektöre en benzer (Cosine) kayıtları arar.
        """
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            limit=limit,
            with_payload=True
        ).points
        return results
