"""Deterministic, question-aware context selection with verbatim quote windows."""

import re


def pack_evidence(sources, question: str, *, limit: int = 10, window: int = 2000):
    terms = set(re.findall(r"\w{3,}", question.lower()))
    ranked = []
    for source in sources:
        text = source.evidence
        # Overlap keeps sentences near a window boundary available for quoting.
        windows = [(offset, text[offset : offset + window]) for offset in range(0, len(text), window // 2)]
        if not windows:
            continue
        scored = [
            (len(terms & set(re.findall(r"\w{3,}", passage.lower()))), -offset, passage) for offset, passage in windows
        ]
        score, negative_offset, passage = max(scored)
        ranked.append(
            (
                score,
                source.citation,
                {
                    "citation": source.citation,
                    "title": source.title,
                    "untrusted_evidence": passage,
                    "evidence_offset": -negative_offset,
                    "evidence_truncated": len(passage) < len(text),
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]
