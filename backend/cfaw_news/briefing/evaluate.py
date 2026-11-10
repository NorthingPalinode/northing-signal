"""Small real-material development comparison. No model calls, seals or control framework."""

import json
import re

from .models import assessment_of, now
from .understand import POLICY_HASH


def compare(store, reference, split="all"):
    labels = [json.loads(line) for line in reference.read_text("utf-8").splitlines() if line.strip()]
    if len({r["version"] for r in labels}) != len(labels):
        raise ValueError("duplicate_reference_version")
    labels = [r for r in labels if split == "all" or r["split"] == split]
    decisive = [r for r in labels if r["decision"] in {"read", "skip"}]
    judgments = store.judgments()
    materials = {r["version"]: store.material(r["version"]) for r in labels}

    def quality(row):
        raw = judgments.get(row["version"])
        if not raw:
            return None
        a = assessment_of(raw)
        score = a.significance * 3 + a.novelty * 2 + a.usefulness
        return a.relevance == "ai" and bool(a.claims) and a.evidence != "insufficient" and score >= 9

    def keywords(row):
        material = materials[row["version"]]
        if not material:
            return None
        return bool(re.search(r"\b(ai|llm|gpt|agent|transformer)\b|人工智能|大模型|智能体",
                              material.title + " " + material.text, re.I))

    def metrics(predict):
        answered, correct, tp, fp, fn = 0, 0, 0, 0, 0
        errors = []
        for row in decisive:
            prediction = predict(row)
            if prediction is None:
                errors.append({"title": row["title"], "type": "not_processed"})
                continue
            answered += 1
            expected = row["decision"] == "read"
            correct += prediction == expected
            tp += prediction and expected
            fp += prediction and not expected
            fn += not prediction and expected
            if prediction != expected:
                errors.append({"title": row["title"], "type": "false_positive" if prediction else "false_negative"})
        return {"answered": answered, "decisive": len(decisive),
                "coverage": round(answered / len(decisive), 3) if decisive else None,
                "complete_accuracy": round(correct / len(decisive), 3) if decisive else None,
                "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall_on_answered": round(tp / (tp + fn), 3) if tp + fn else None,
                "tp": tp, "fp": fp, "fn": fn, "errors": errors}

    return {"at": now(), "profile": "ai_development", "split": split,
            "policy": POLICY_HASH, "reference_cases": len(labels),
            "families": len({r["family"] for r in labels}),
            "uncertain_excluded": len(labels) - len(decisive),
            "keyword_filter": metrics(keywords), "content_quality": metrics(quality),
            "limitations": ["AI authored labels; no human utility measurement or independent validation.",
                            "Small selected development sample; document quality does not measure event grouping recall.",
                            "Pending or rejected model output counts against complete accuracy."]}
