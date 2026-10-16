"""Strict Unicode scoring with maximum-cardinality one-to-one polygon matching."""
import re
import numpy as np
import regex
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Polygon, Point


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def iou(a, b):
    a, b = Polygon(a), Polygon(b)
    union = a.union(b).area
    return a.intersection(b).area / union if union else 0.0


def in_region(prediction, polygon):
    center = Polygon(prediction["polygon"]).centroid
    return Polygon(polygon).covers(Point(center.x, center.y))


def match_regions(reference, predictions, threshold=0.5):
    if not reference or not predictions:
        return []
    overlaps = np.array([[iou(a["polygon"], b["polygon"]) for b in predictions] for a in reference])
    # A valid pair outweighs all possible IoU tie-breaks, maximizing cardinality first.
    reward = (overlaps >= threshold) * (min(overlaps.shape) + 1 + overlaps)
    rows, cols = linear_sum_assignment(reward, maximize=True)
    return [(int(r), int(c), float(overlaps[r, c])) for r, c in zip(rows, cols) if overlaps[r, c] >= threshold]


def rates(tp, predicted, expected):
    p = tp / predicted if predicted else (1.0 if expected == 0 else 0.0)
    r = tp / expected if expected else 1.0
    return {"precision": p, "recall": r, "f1": 2*p*r/(p+r) if p+r else 0.0,
            "tp": tp, "predicted": predicted, "expected": expected}


def quality(annotation, predictions, threshold=0.5):
    if not annotation.get("reviewed") or not annotation.get("complete"):
        return None
    ignored = [r for r in annotation["regions"] if r.get("ignore")]
    predictions = [p for p in predictions if not any(iou(p["polygon"], r["polygon"]) >= threshold for r in ignored)]
    refs = [r for r in annotation["regions"] if not r.get("ignore")]
    matches = match_regions(refs, predictions, threshold)
    matched_r, matched_p = {m[0] for m in matches}, {m[1] for m in matches}
    edits = grapheme_edits = chars = graphemes = exact = 0
    per_language = {}
    for i, r in enumerate(refs):
        j = next((j for ri, j, _ in matches if ri == i), None)
        actual = predictions[j]["text"] if j is not None else ""
        expected = r["text"]
        d = edit_distance(expected, actual)
        edits += d
        chars += len(expected)
        eg, ag = regex.findall(r"\X", expected), regex.findall(r"\X", actual)
        grapheme_edits += edit_distance(eg, ag)
        graphemes += len(eg)
        exact += int(j is not None and expected == actual)
        group = per_language.setdefault(r.get("language", "unknown"), {"edits": 0, "characters": 0, "exact": 0, "regions": 0})
        group["edits"] += d
        group["characters"] += len(expected)
        group["exact"] += int(j is not None and expected == actual)
        group["regions"] += 1
    for j, p in enumerate(predictions):
        if j not in matched_p:
            edits += len(p["text"])
            grapheme_edits += len(regex.findall(r"\X", p["text"]))
    return {"detection": rates(len(matches), len(predictions), len(refs)),
            "e2e": rates(exact, len(predictions), len(refs)),
            "cer": edits/chars if chars else None, "character_edits": edits, "reference_characters": chars,
            "grapheme_error_rate": grapheme_edits/graphemes if graphemes else None,
            "mean_iou": float(np.mean([m[2] for m in matches])) if matches else None,
            "misses": len(refs)-len(matched_r), "extra_regions": len(predictions)-len(matched_p),
            "screen_exact": exact == len(refs) == len(predictions), "by_language": per_language,
            "negative_input": not refs, "false_text_regions": len(predictions) if not refs else None,
            "word_error_rate": None, "word_tokenization": "not configured; whitespace is not valid for every script",
            "policy": "strict-unicode-v1; source polygon IoU; unmatched predictions count as insertions",
            "matches": [{"reference": i, "prediction": j, "iou": overlap} for i,j,overlap in matches]}


def application(annotation, predictions):
    labels, fields = [], []
    for query in annotation.get("labels", []):
        normalize = (lambda s: s) if query.get("case_sensitive", True) else str.casefold
        matches = [p for p in predictions if normalize(p["text"]) == normalize(query["text"])
                   and (not query.get("polygon") or in_region(p, query["polygon"]))]
        threshold = query.get("min_confidence")
        accepted = [p for p in matches if threshold is None or (p.get("confidence") is not None and p["confidence"] >= threshold)]
        state = "present" if accepted else "uncertain" if matches else "absent"
        correct = (state == "present") == query.get("present", True) if state != "uncertain" else None
        labels.append({**query, "state": state, "correct": correct, "evidence": matches})
    for field in annotation.get("fields", []):
        found = sorted([p for p in predictions if in_region(p, field["polygon"])], key=lambda p: (min(x[1] for x in p["polygon"]), min(x[0] for x in p["polygon"])))
        raw = " ".join(p["text"] for p in found)
        value, unit, parse_error = raw if found else None, None, None
        if field.get("parser") == "number" and found:
            separator = re.escape(field.get("decimal_separator", "."))
            match = re.fullmatch(rf"\s*([+-]?\d+(?:{separator}\d+)?)\s*([^\d]*)", raw)
            if match:
                value, unit = match.group(1), match.group(2).strip()
            else:
                value, parse_error = None, "Expected one numeric value and optional unit"
        fields.append({**field, "raw": raw, "value": value, "unit": unit, "parse_error": parse_error,
                       "correct": raw == field["expected"] if field.get("expected") is not None else None,
                       "evidence": found})
    negative = [l for l in labels if not l.get("present", True)]
    positive = [l for l in labels if l.get("present", True)]
    return {"labels": labels, "fields": fields,
            "false_pass_rate": sum(l["state"] == "present" for l in negative)/len(negative) if negative else None,
            "false_fail_rate": sum(l["state"] == "absent" for l in positive)/len(positive) if positive else None,
            "uncertain": sum(l["state"] == "uncertain" for l in labels),
            "correct_query_coverage": sum(l["correct"] is True for l in labels)/len(labels) if labels else None}
