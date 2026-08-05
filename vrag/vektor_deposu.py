"""Qdrant vektör deposu sarmalayıcı.

Docker'sız, embedded/local modda çalışır (QdrantClient(path=...)). Tek koleksiyon
qdrant_db/ altında. Koleksiyon kurma (idempotent), toplu ekleme ve kategori-filtreli
arama sağlar.
"""
from __future__ import annotations

import uuid

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from . import config


class VektorDeposu:
    """Qdrant koleksiyonu üzerinde ince bir sarmalayıcı."""

    def __init__(self, koleksiyon: str = config.KOLEKSIYON_ADI):
        config.QDRANT_YOLU.mkdir(parents=True, exist_ok=True)
        self.istemci = QdrantClient(path=str(config.QDRANT_YOLU))
        self.koleksiyon = koleksiyon

    def kapat(self) -> None:
        """Qdrant istemcisini kapatır (embedded modda dosya kilidini serbest bırakır)."""
        self.istemci.close()

    def __enter__(self) -> "VektorDeposu":
        return self

    def __exit__(self, *_) -> None:
        self.kapat()

    def koleksiyon_kur(self, boyut: int, sifirla: bool = True) -> None:
        """Koleksiyonu oluşturur. sifirla=True ise varsa önce siler (idempotent)."""
        if self.istemci.collection_exists(self.koleksiyon):
            if sifirla:
                self.istemci.delete_collection(self.koleksiyon)
            else:
                return
        self.istemci.create_collection(
            collection_name=self.koleksiyon,
            vectors_config=VectorParams(size=boyut, distance=Distance.COSINE),
        )

    def ekle(self, vektorler: np.ndarray, payloadlar: list[dict]) -> int:
        """Vektörleri payload'larıyla toplu ekler; eklenen nokta sayısını döndürür."""
        if len(vektorler) != len(payloadlar):
            raise ValueError("vektör ve payload sayısı eşleşmiyor")
        if len(vektorler) == 0:
            return 0
        noktalar = [
            PointStruct(id=str(uuid.uuid4()), vector=vek.tolist(), payload=pl)
            for vek, pl in zip(vektorler, payloadlar)
        ]
        self.istemci.upsert(collection_name=self.koleksiyon, points=noktalar, wait=True)
        return len(noktalar)

    def ara(self, vektor: np.ndarray, limit: int, filtreler: dict | None = None):
        """Sorgu vektörüne en yakın noktaları döndürür (ScoredPoint listesi).

        filtreler: {payload_alani: deger} -> tümü sağlanmalı (AND). Boş değerler
        yok sayılır. Örn: {"kategori": "Savaş Uçağı", "ulke": "Türkiye"}.
        """
        suzgec = None
        if filtreler:
            kosullar = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filtreler.items() if v
            ]
            if kosullar:
                suzgec = Filter(must=kosullar)
        yanit = self.istemci.query_points(
            collection_name=self.koleksiyon,
            query=vektor.tolist(),
            limit=limit,
            query_filter=suzgec,
            with_payload=True,
        )
        return yanit.points

    def sayim(self) -> int:
        """Koleksiyondaki toplam nokta (vektör) sayısı."""
        return self.istemci.count(collection_name=self.koleksiyon).count


def indeks_var() -> bool:
    """İndeks diskte kurulu mu? (istemci açmadan hızlı kontrol)"""
    return (config.QDRANT_YOLU / "collection" / config.KOLEKSIYON_ADI).exists()
