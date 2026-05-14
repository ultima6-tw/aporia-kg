"""
Obsidian-style knowledge extractor.

Converts any document into atomic notes using Gemini:
  {title, summary, links}
  - title:   concept name (short, consistent)
  - summary: what this document says about it (1-3 sentences)
  - links:   related concept titles found in the same document

Large documents use map-reduce:
  1. Split by PDF TOC chapters (if available) or evenly (~50k chars/segment)
  2. Extract local notes per segment
  3. Consolidate all local notes → final notes
  4. Repeat consolidation if still too large
"""
from __future__ import annotations

import json
import os
import re

MAX_SEGMENT_CHARS  = 180_000   # ~45k tokens, safe for gemini-2.5-flash
MAX_NOTES_FOR_CONSOLIDATION = 200  # if total notes exceed this, consolidate again

_EXTRACT_SYSTEM = "You are a knowledge extraction assistant. Output only valid JSON, no markdown fences."

_EXTRACT_PROMPT = """\
Read the following document and extract atomic knowledge notes in Obsidian style.

For each distinct concept, method, tool, decision, finding, or entity:
- title: short concept name (2-6 words, consistent naming)
- summary: 1-3 sentences — what THIS document says about it
- links: list of other concept titles (from this same document) that it connects to

Rules:
- One note per concept
- Titles must be consistent (same concept = same title)
- Links must only reference titles that appear in your response
- Aim for 5-30 notes depending on document length and density
- If the document has little meaningful content, return fewer notes (even 0)

Return a JSON array only:
[
  {{"title": "...", "summary": "...", "links": ["...", "..."]}}
]

Document:
{text}
"""

_CONSOLIDATE_PROMPT = """\
The following are Obsidian-style notes extracted from different sections of the same document.
Consolidate them:
- Merge notes with the same or very similar title into one
- Combine summaries (keep the most informative content, 1-4 sentences)
- Union their links, remove self-references
- Drop duplicate or near-identical notes

Return a JSON array only:
[
  {{"title": "...", "summary": "...", "links": ["...", "..."]}}
]

Notes to consolidate:
{notes_json}
"""


def _call_gemini(prompt: str) -> list[dict]:
    """Call Gemini with temperature=0 for reliable JSON output."""
    import os
    from pathlib import Path
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_EXTRACT_SYSTEM,
            temperature=0,
        ),
    )
    raw = (resp.text or "").strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw.strip())


def _extract_segment(text: str) -> list[dict]:
    """Extract notes from a single text segment."""
    try:
        notes = _call_gemini(_EXTRACT_PROMPT.format(text=text))
        return [n for n in notes if isinstance(n, dict) and n.get("title")]
    except Exception as e:
        print(f"[extractor] segment extraction failed: {e}")
        return []


def _consolidate_notes(notes: list[dict]) -> list[dict]:
    """Merge and deduplicate a list of notes via Gemini."""
    if not notes:
        return []
    try:
        result = _call_gemini(_CONSOLIDATE_PROMPT.format(
            notes_json=json.dumps(notes, ensure_ascii=False, indent=2)
        ))
        return [n for n in result if isinstance(n, dict) and n.get("title")]
    except Exception as e:
        print(f"[extractor] consolidation failed: {e}")
        return notes  # fall back to original if consolidation fails


def _split_evenly(text: str, max_chars: int = MAX_SEGMENT_CHARS) -> list[str]:
    """Split text into segments of at most max_chars, breaking at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    segments = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            segments.append(text[start:])
            break
        # Try to break at a paragraph boundary
        boundary = text.rfind("\n\n", start, end)
        if boundary == -1 or boundary <= start:
            boundary = text.rfind("\n", start, end)
        if boundary == -1 or boundary <= start:
            boundary = end
        segments.append(text[start:boundary])
        start = boundary
    return [s.strip() for s in segments if s.strip()]


def _split_by_toc(pdf_path: str) -> list[str] | None:
    """
    Try to split PDF by its outline/bookmarks.
    Returns list of chapter texts, or None if no usable TOC found.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        outline = reader.outline
        if not outline or len(outline) < 2:
            return None

        # Collect page numbers for each top-level chapter
        def get_page_num(item) -> int | None:
            try:
                return reader.get_destination_page_number(item)
            except Exception:
                return None

        chapters = []
        for item in outline:
            if isinstance(item, list):
                continue  # skip nested outlines for now
            pg = get_page_num(item)
            if pg is not None:
                chapters.append(pg)

        if len(chapters) < 2:
            return None

        chapters = sorted(set(chapters))
        segments = []
        all_pages = [page.extract_text() or "" for page in reader.pages]

        for i, start_pg in enumerate(chapters):
            end_pg = chapters[i + 1] if i + 1 < len(chapters) else len(all_pages)
            segment_text = "\n".join(all_pages[start_pg:end_pg])
            for tok in ["<|endoftext|>", "<|im_start|>", "<|im_end|>"]:
                segment_text = segment_text.replace(tok, " ")
            if segment_text.strip():
                segments.append(segment_text.strip())

        return segments if segments else None
    except Exception as e:
        print(f"[extractor] TOC split failed: {e}")
        return None


def extract_notes_from_pdf(pdf_path: str) -> list[dict]:
    """Extract Obsidian notes from a PDF file."""
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for tok in ["<|endoftext|>", "<|im_start|>", "<|im_end|>"]:
        full_text = full_text.replace(tok, " ")

    if len(full_text) <= MAX_SEGMENT_CHARS:
        return _extract_segment(full_text)

    # Try TOC split first
    segments = _split_by_toc(pdf_path)
    if segments is None:
        segments = _split_evenly(full_text)

    print(f"[extractor] PDF split into {len(segments)} segments")
    return _map_reduce(segments)


def extract_notes_from_text(text: str) -> list[dict]:
    """Extract Obsidian notes from plain text."""
    if len(text) <= MAX_SEGMENT_CHARS:
        return _extract_segment(text)
    segments = _split_evenly(text)
    print(f"[extractor] text split into {len(segments)} segments")
    return _map_reduce(segments)


def _map_reduce(segments: list[str]) -> list[dict]:
    """
    Map-reduce extraction for large documents.
    Round 1: extract notes per segment.
    Round 2+: consolidate until notes fit in one pass.
    """
    # Map: extract notes per segment
    all_notes: list[dict] = []
    for i, seg in enumerate(segments, 1):
        print(f"[extractor] segment {i}/{len(segments)} ({len(seg):,} chars)")
        notes = _extract_segment(seg)
        print(f"[extractor]   → {len(notes)} notes")
        all_notes.extend(notes)

    # Reduce: consolidate until convergence
    round_num = 2
    while len(all_notes) > MAX_NOTES_FOR_CONSOLIDATION:
        notes_json_size = len(json.dumps(all_notes, ensure_ascii=False))
        print(f"[extractor] consolidation round {round_num}: {len(all_notes)} notes ({notes_json_size:,} chars)")
        if notes_json_size <= MAX_SEGMENT_CHARS:
            all_notes = _consolidate_notes(all_notes)
            break
        # Too large for one consolidation call — consolidate in batches
        batch_size = MAX_NOTES_FOR_CONSOLIDATION // 2
        batches = [all_notes[i:i+batch_size] for i in range(0, len(all_notes), batch_size)]
        consolidated = []
        for b in batches:
            consolidated.extend(_consolidate_notes(b))
        all_notes = consolidated
        round_num += 1

    # Final consolidation pass
    if len(all_notes) > 0:
        notes_json_size = len(json.dumps(all_notes, ensure_ascii=False))
        if notes_json_size <= MAX_SEGMENT_CHARS:
            all_notes = _consolidate_notes(all_notes)

    print(f"[extractor] final: {len(all_notes)} notes")
    return all_notes
