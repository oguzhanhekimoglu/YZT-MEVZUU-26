"""VRAG — Teknofest hava aracı tanıma (tek encoder, retrieval-only Visual RAG).

Boru hattı (2 katman): YOLO crop -> SigLIP2 embedding -> Qdrant retrieval.
Nihai cevap = en benzer referansın modeli (retrieval top-1).
"""

__version__ = "1.0.0"
