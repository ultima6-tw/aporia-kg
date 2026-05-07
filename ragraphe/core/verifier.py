"""
KB connection verifier — pure system computation, no LLM.

Primary use case: ground-truth-free agent evaluation.
When an AI agent claims "concept A is related to concept B," this module
verifies that claim using only KB evidence, bypassing the circular-trust
problem of using LLM-as-judge (i.e., asking an LLM to judge an LLM's output).
All measurements are system-generated from embeddings and document statistics —
no language model is involved in the verification path.

Agent evaluation workflow:
  1. Import domain knowledge into the KB (manuals, papers, code docs)
  2. Run the agent on tasks that produce factual claims
  3. Call verify_connection() for each claim — the system returns a numeric
     score backed by KB evidence, not a model's opinion
  4. Accumulate reports across multiple verifier_ids to build consensus

Signals used:
  1. embedding_similarity   — cosine similarity of concept embeddings
  2. co_mention_count       — chunks that mention both concepts (excl. verify:// sources)
  3. weighted_source_score  — sum of credibility weights of supporting sources

Each call stores a verification report in ChromaDB (source = verify://A::B),
so confidence accumulates across independent verifications.
"""
from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime


# ── Cosine similarity (pure Python, no numpy dependency) ─────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Canonical key (order-independent) ────────────────────────────────────────

def _verify_key(a: str, b: str) -> str:
    lo, hi = sorted([a.strip().lower(), b.strip().lower()])
    return f"verify://{lo}::{hi}"


# ── Core verification (accepts pre-computed vectors) ─────────────────────────

def _verify_core(a: str, b: str, vec_a: list[float], vec_b: list[float],
                 verifier_id: str = "system") -> dict:
    """
    Inner verification logic. Accepts pre-computed embeddings to avoid
    redundant embed calls when running batch audits.

    Returns {"report": {...}, "fix_hints": {...}} where fix_hints lists
    which KB sources cover each concept independently — useful for locating
    where to add missing documentation when co_mention_count is 0.
    """
    from ragraphe.core.crawler import query_raw_chunks, raw_chunks
    from ragraphe.db.store import get_credibilities_for_sources

    b_lower, a_lower = b.lower(), a.lower()
    key = _verify_key(a, b)

    # ── 1. Embedding-level similarity ─────────────────────────────────────────
    embedding_similarity = round(_cosine_similarity(vec_a, vec_b), 4)

    near_a = [c for c in query_raw_chunks(vec_a, n=10)
              if not c.get("source", "").startswith("verify://")]
    near_b = [c for c in query_raw_chunks(vec_b, n=10)
              if not c.get("source", "").startswith("verify://")]

    bidirectional = (
        any(b_lower in c["text"].lower() for c in near_a) and
        any(a_lower in c["text"].lower() for c in near_b)
    )

    # ── 2. Co-mention count ───────────────────────────────────────────────────
    try:
        hits = raw_chunks.get(
            where_document={"$contains": a},
            include=["documents", "metadatas"],
        )
        co_mention_chunks = [
            {"text": doc, "source": meta.get("source", "")}
            for doc, meta in zip(hits.get("documents", []), hits.get("metadatas", []))
            if b_lower in doc.lower()
            and not meta.get("source", "").startswith("verify://")
        ]
    except Exception:
        co_mention_chunks = []

    co_mention_count   = len(co_mention_chunks)
    co_mention_sources = {c["source"] for c in co_mention_chunks if c["source"]}

    # ── 3. KB coverage ────────────────────────────────────────────────────────
    coverage_sources_a = {c["source"] for c in near_a}
    coverage_sources_b = {c["source"] for c in near_b}
    kb_coverage_a = round(min(1.0, len(coverage_sources_a) / 5), 3)
    kb_coverage_b = round(min(1.0, len(coverage_sources_b) / 5), 3)
    data_sufficient = kb_coverage_a > 0.1 and kb_coverage_b > 0.1

    # ── 4. Weighted source score ──────────────────────────────────────────────
    supporting_sources    = co_mention_sources | coverage_sources_a | coverage_sources_b
    credibilities         = get_credibilities_for_sources(list(supporting_sources))
    weighted_source_score = round(sum(credibilities.values()), 3)

    # ── 5. Prior independent verifications ───────────────────────────────────
    try:
        prior = raw_chunks.get(where={"source": key}, include=["metadatas"])
        prior_verifier_ids = {m.get("verifier_id", "") for m in prior.get("metadatas", [])}
        prior_verifier_ids.discard("")
        prior_verifications = len(prior_verifier_ids)
    except Exception:
        prior_verifications = 0

    # ── 6. kb_support_score ───────────────────────────────────────────────────
    # Weights: similarity 40 %, co-mention 30 %, source credibility 30 %
    # Normalisation: 5 co-mentions = full score; weighted_score 2.0 = full score
    kb_support_score = round(
        0.4 * embedding_similarity
        + 0.3 * min(1.0, co_mention_count / 5)
        + 0.3 * min(1.0, weighted_source_score / 2.0),
        4,
    )

    report = {
        "concept_a":           a,
        "concept_b":           b,
        "verified_at":         datetime.utcnow().isoformat(),
        "verifier_id":         verifier_id,
        "kb_support_score":    kb_support_score,
        "details": {
            "embedding_similarity":  embedding_similarity,
            "bidirectional":         bidirectional,
            "co_mention_count":      co_mention_count,
            "weighted_source_score": weighted_source_score,
            "kb_coverage_a":         kb_coverage_a,
            "kb_coverage_b":         kb_coverage_b,
        },
        "prior_verifications": prior_verifications,
        "data_sufficient":     data_sufficient,
    }

    # ── 7. Store report in ChromaDB ───────────────────────────────────────────
    try:
        raw_chunks.upsert(
            ids        = [str(uuid.uuid4())],
            embeddings = [vec_a],
            documents  = [json.dumps(report, ensure_ascii=False)],
            metadatas  = [{
                "source":       key,
                "source_name":  f"Verification: {a} ↔ {b}",
                "category":     "verification",
                "verifier_id":  verifier_id,
                "lang_en":      True,
                "lang_zh":      False,
                "lang_ja":      False,
            }],
        )
    except Exception:
        pass

    # ── 8. Fix hints (returned separately, not stored) ────────────────────────
    only_a = sorted(coverage_sources_a - coverage_sources_b)
    only_b = sorted(coverage_sources_b - coverage_sources_a)
    fix_hints = {
        "sources_with_a_only": only_a,
        "sources_with_b_only": only_b,
        "sources_with_both":   sorted(coverage_sources_a & coverage_sources_b),
        "suggested_action": (
            f"Add mention of '{b}' to: {only_a[0]}" if only_a else
            f"Add mention of '{a}' to: {only_b[0]}" if only_b else
            "KB has limited coverage of both concepts — import more relevant content"
        ),
    }

    return {"report": report, "fix_hints": fix_hints}


# ── Public single-pair verification ──────────────────────────────────────────

def verify_connection(concept_a: str, concept_b: str,
                      verifier_id: str = "system") -> dict:
    """
    Verify the connection between two concepts using KB evidence only.
    Returns a structured report with raw measurements and stores it in ChromaDB.

    All numbers are system-computed — no LLM involved.
    """
    from ragraphe.core.crawler import embed_batch

    a, b = concept_a.strip(), concept_b.strip()
    vecs = embed_batch([a, b])
    return _verify_core(a, b, vecs[0], vecs[1], verifier_id)["report"]


# ── Batch audit ───────────────────────────────────────────────────────────────

def audit_connections(
    concepts: list[str] | None = None,
    pairs: list[dict] | None = None,
    pre_filter_threshold: float = 0.3,
    verifier_id: str = "system",
) -> dict:
    """
    Audit KB coverage for a set of concept pairs using a two-stage pipeline:

    Stage 1 — Pre-filter (batch embed + pairwise cosine, no KB queries):
      Pairs with embedding_similarity < pre_filter_threshold are skipped.
      These pairs are semantically distant enough that missing co-mention
      is expected, not a documentation gap.

    Stage 2 — Full verify (only pairs that passed pre-filter):
      Runs complete kb_verify on each pair and stores reports in ChromaDB.

    Returns results grouped as:
      gaps   — co_mention_count == 0 (design intent not documented in KB)
               Each gap includes fix_hints: which sources to add documentation to.
      weak   — co_mention > 0 but kb_support_score < 0.6
      strong — kb_support_score >= 0.6
      skipped — filtered out by pre_filter_threshold
    """
    from ragraphe.core.crawler import embed_batch

    # Build canonical pair list
    all_pairs: list[tuple[str, str]] = []
    if pairs:
        for p in pairs:
            a, b = p.get("a", "").strip(), p.get("b", "").strip()
            if a and b:
                all_pairs.append((a, b))
    elif concepts:
        cs = [c.strip() for c in concepts if c.strip()]
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                all_pairs.append((cs[i], cs[j]))

    if not all_pairs:
        return {"error": "No valid pairs to audit"}

    # Stage 1: batch embed all unique concepts in one call
    unique = list({c for pair in all_pairs for c in pair})
    vecs   = embed_batch(unique)
    vec_map: dict[str, list[float]] = dict(zip(unique, vecs))

    skipped: list[dict] = []
    to_verify: list[tuple[str, str, float]] = []

    for a, b in all_pairs:
        sim = round(_cosine_similarity(vec_map[a], vec_map[b]), 4)
        if sim < pre_filter_threshold:
            skipped.append({
                "concept_a": a, "concept_b": b,
                "embedding_similarity": sim,
                "reason": "below_pre_filter_threshold",
            })
        else:
            to_verify.append((a, b, sim))

    # Stage 2: full verify for pairs that passed the pre-filter
    gaps:   list[dict] = []
    weak:   list[dict] = []
    strong: list[dict] = []

    for a, b, _ in to_verify:
        result = _verify_core(a, b, vec_map[a], vec_map[b], verifier_id)
        report = result["report"]
        entry  = {
            "concept_a":        a,
            "concept_b":        b,
            "kb_support_score": report["kb_support_score"],
            "details":          report["details"],
            "data_sufficient":  report["data_sufficient"],
        }
        if report["details"]["co_mention_count"] == 0:
            entry["fix_hints"] = result["fix_hints"]
            gaps.append(entry)
        elif report["kb_support_score"] < 0.6:
            weak.append(entry)
        else:
            strong.append(entry)

    gaps.sort(key=lambda x: x["kb_support_score"])
    weak.sort(key=lambda x: x["kb_support_score"])

    run_id  = str(uuid.uuid4())
    run_at  = datetime.utcnow().isoformat()
    results = {"gaps": gaps, "weak": weak, "strong": strong, "skipped": skipped}

    try:
        from ragraphe.db.store import record_audit_run
        record_audit_run(run_id, run_at, results, verifier_id)
    except Exception:
        pass

    return {
        "run_id": run_id,
        "run_at": run_at,
        "summary": {
            "total_pairs":            len(all_pairs),
            "skipped_by_prefilter":   len(skipped),
            "verified":               len(to_verify),
            "gaps":                   len(gaps),
            "weak":                   len(weak),
            "strong":                 len(strong),
            "pre_filter_threshold":   pre_filter_threshold,
        },
        "gaps":    gaps,
        "weak":    weak,
        "strong":  strong,
        "skipped": skipped,
    }


# ── KB Completeness Report ────────────────────────────────────────────────────

def _fmt_markdown(data: dict) -> str:
    """Format the report data as a Markdown document."""
    now      = data["generated_at"]
    sources  = data["sources"]
    watchlist = data["watchlist"]
    audit    = data.get("current_audit")
    hist     = data["audit_history_summary"]
    files    = data["file_watches"]

    lines: list[str] = []
    lines.append(f"# KB Completeness Report")
    lines.append(f"Generated: {now} UTC\n")

    # ── Sources ──────────────────────────────────────────────────────────────
    total_chunks = sum(s.get("count", 0) for s in sources)
    lines.append(f"## Knowledge Sources ({len(sources)} sources, {total_chunks:,} chunks)\n")
    if sources:
        lines.append("| Source | Chunks | Credibility |")
        lines.append("|--------|-------:|------------:|")
        for s in sources:
            lines.append(f"| {s['source']} | {s.get('count', 0):,} | {s.get('credibility', 0.5):.2f} |")
    else:
        lines.append("_No sources imported yet._")
    lines.append("")

    # ── Watchlist + current audit ─────────────────────────────────────────────
    lines.append(f"## Audit Watchlist ({len(watchlist)} concepts)\n")
    if watchlist:
        lines.append("Monitored: " + ", ".join(f"`{c}`" for c in watchlist) + "\n")
    else:
        lines.append("_No concepts in watchlist. Use `kb_watch_concepts` to add._\n")

    if audit and watchlist:
        s = audit.get("summary", {})
        n_gap    = s.get("gaps", 0)
        n_weak   = s.get("weak", 0)
        n_strong = s.get("strong", 0)
        n_skip   = s.get("skipped_by_prefilter", 0)

        lines.append("## Current Coverage Status\n")
        lines.append(f"- ✅ **Strong** (score ≥ 0.6): {n_strong} pairs")
        lines.append(f"- ⚠️  **Weak** (co_mention > 0, score < 0.6): {n_weak} pairs")
        lines.append(f"- ❌ **Gap** (co_mention = 0): {n_gap} pairs")
        if n_skip:
            lines.append(f"- ⏭️  Skipped by pre-filter (embedding similarity < {s.get('pre_filter_threshold', 0.3)}): {n_skip} pairs")
        lines.append("")

        if audit.get("gaps"):
            lines.append("### Gaps — Action Required\n")
            for i, g in enumerate(audit["gaps"], 1):
                a, b = g["concept_a"], g["concept_b"]
                score = g.get("kb_support_score", 0)
                hint  = g.get("fix_hints", {}).get("suggested_action", "")
                lines.append(f"{i}. **`{a}`** ↔ **`{b}`** (score: {score:.4f})")
                if hint:
                    lines.append(f"   → _{hint}_")
            lines.append("")

        if audit.get("weak"):
            lines.append("### Weak — Needs More Coverage\n")
            for g in audit["weak"]:
                a, b = g["concept_a"], g["concept_b"]
                cm   = g.get("details", {}).get("co_mention_count", 0)
                score = g.get("kb_support_score", 0)
                lines.append(f"- **`{a}`** ↔ **`{b}`** (score: {score:.4f}, co_mention: {cm})")
            lines.append("")

        if audit.get("strong"):
            lines.append("### Strong — Well Documented\n")
            for g in audit["strong"]:
                a, b = g["concept_a"], g["concept_b"]
                cm   = g.get("details", {}).get("co_mention_count", 0)
                score = g.get("kb_support_score", 0)
                lines.append(f"- **`{a}`** ↔ **`{b}`** (score: {score:.4f}, co_mention: {cm})")
            lines.append("")

    # ── History summary ───────────────────────────────────────────────────────
    lines.append("## Audit History\n")
    if hist.get("total_entries", 0):
        by_s = hist.get("by_status", {})
        lines.append(f"Total runs: **{hist['total_runs']}** | Total entries: **{hist['total_entries']}**\n")
        lines.append("| Status | Count |")
        lines.append("|--------|------:|")
        for st, n in sorted(by_s.items()):
            icon = {"gap": "❌", "weak": "⚠️", "strong": "✅", "skipped": "⏭️"}.get(st, "")
            lines.append(f"| {icon} {st} | {n} |")
    else:
        lines.append("_No audit runs recorded yet._")
    lines.append("")

    # ── Synced files ──────────────────────────────────────────────────────────
    lines.append("## Synced Files\n")
    if files:
        lines.append("| File | Source | Last Synced | Status |")
        lines.append("|------|--------|-------------|--------|")
        for f in files:
            synced = (f.get("last_synced") or "never")[:16]
            stale  = f.get("stale")
            status = "⚠️ stale" if stale else ("✓ current" if stale is False else "—")
            short  = f["file_path"].replace(os.path.expanduser("~"), "~")
            lines.append(f"| `{short}` | {f['source_name']} | {synced} | {status} |")
    else:
        lines.append("_No files registered. Use `kb_sync_file` to register and sync files._")
    lines.append("")

    return "\n".join(lines)


def generate_report(format: str = "markdown", verifier_id: str = "report") -> str | dict:
    """
    Generate a KB completeness report combining:
    - Knowledge sources (imported content, chunk counts, credibility)
    - Audit watchlist + live coverage status (gaps, weak, strong)
    - Audit history summary (trend across all past runs)
    - Synced files and their freshness

    Args:
        format:      "markdown" (default) for a human-readable document,
                     "json" for structured data
        verifier_id: Identifier for the audit run triggered by this report
    """
    from ragraphe.core.crawler import list_chunk_sources
    from ragraphe.db.store import (
        list_watch_concepts, get_audit_summary, list_file_watches,
        get_credibilities_for_sources,
    )

    now = datetime.utcnow().isoformat()[:16]

    # Sources
    sources = list_chunk_sources()
    creds   = get_credibilities_for_sources([s["source"] for s in sources])
    for s in sources:
        s["credibility"] = creds.get(s["source"], 0.5)
    sources.sort(key=lambda s: s.get("count", 0), reverse=True)

    # Watchlist + live audit
    watchlist = list_watch_concepts()
    current_audit = audit_connections(concepts=watchlist, verifier_id=verifier_id) if watchlist else None

    # History
    history_summary = get_audit_summary()

    # Synced files + staleness check
    file_watches = list_file_watches()
    for fw in file_watches:
        try:
            mtime = os.path.getmtime(fw["file_path"])
            fw["stale"] = mtime > (fw["last_mtime"] or 0)
        except Exception:
            fw["stale"] = None

    data = {
        "generated_at":        now,
        "sources":             sources,
        "watchlist":           watchlist,
        "current_audit":       current_audit,
        "audit_history_summary": history_summary,
        "file_watches":        file_watches,
    }

    return _fmt_markdown(data) if format == "markdown" else data
