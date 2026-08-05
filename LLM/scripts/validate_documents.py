"""Validate the canonical document manifest, role roots, and real checksums."""

from __future__ import annotations

import json
from pathlib import Path

from operational_decision.rag.document_catalog import DocumentCatalog

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Validate all delivered documents and print the controlled role counts."""
    catalog = DocumentCatalog(ROOT / "data/rag/document_manifest.yaml")
    catalog.validate()
    result = {
        "document_count": len(catalog.documents),
        "runtime_rag_count": len(catalog.runtime_documents),
        "reference_only_count": len(catalog.reference_only_documents),
        "document_manifest_sha256": catalog.manifest_sha256,
        "status": "VALID",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()