#!/usr/bin/env python3
"""
Reindex display_categories for all existing ChromaDB chunks.

For each chunk:
  - Re-runs infer_display_categories(text, db_cat) with the new multi-category logic
  - Writes the result back as "display_categories" (comma-separated string)
  - Preserves all other metadata fields unchanged

Run from the project root:
    python scripts/reindex_display_categories.py [--dry-run] [--backend gemini|ollama]

Options:
    --dry-run      Print stats without writing anything
    --backend      Override LLM_BACKEND env var (affects which collection is used)
    --batch-size   Chunks per update batch (default: 200)
"""
import argparse
import os
import sys

# Allow importing ragraphe from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run",    action="store_true", help="Show stats without writing")
    parser.add_argument("--backend",    default=None,        help="gemini or ollama (default: LLM_BACKEND env)")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    backend = args.backend or os.getenv("LLM_BACKEND", "ollama").lower()
    os.environ["LLM_BACKEND"] = backend  # ensure ragraphe modules pick up the right backend

    import chromadb
    from ragraphe.db.store import _chroma
    from ragraphe.core.category import infer_display_categories

    col_name = f"raw_chunks_{backend}"
    try:
        col = _chroma.get_collection(col_name)
    except Exception:
        print(f"[error] Collection '{col_name}' not found. Have you run the crawler with backend={backend}?")
        sys.exit(1)

    total = col.count()
    print(f"Collection : {col_name}")
    print(f"Total chunks: {total}")
    if total == 0:
        print("Nothing to do.")
        return

    updated = 0
    skipped = 0
    batch_size = args.batch_size

    for offset in range(0, total, batch_size):
        result = col.get(
            limit=batch_size,
            offset=offset,
            include=["documents", "metadatas"],
        )
        ids       = result["ids"]
        docs      = result["documents"]
        metadatas = result["metadatas"]

        new_ids   = []
        new_metas = []

        for chunk_id, text, meta in zip(ids, docs, metadatas):
            db_cat = meta.get("category", "general")
            cats   = infer_display_categories(text, db_cat)
            new_val = ",".join(cats)

            old_val = meta.get("display_categories") or meta.get("display_category") or ""
            if new_val == old_val:
                skipped += 1
                continue

            new_meta = dict(meta)
            new_meta["display_categories"] = new_val
            # Remove legacy single-value field if present
            new_meta.pop("display_category", None)

            new_ids.append(chunk_id)
            new_metas.append(new_meta)

        if new_ids and not args.dry_run:
            col.update(ids=new_ids, metadatas=new_metas)

        updated += len(new_ids)
        done = min(offset + batch_size, total)
        print(f"  {done}/{total}  updated={updated}  skipped={skipped}", end="\r")

    print()  # newline after progress line
    if args.dry_run:
        print(f"[dry-run] would update {updated} chunks, skip {skipped} unchanged")
    else:
        print(f"Done. Updated {updated} chunks, skipped {skipped} unchanged.")


if __name__ == "__main__":
    main()
