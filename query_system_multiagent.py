from __future__ import annotations

import re
from typing import Any

from agents.a5_template import build_template_pipeline


PIPELINE = build_template_pipeline()


def _extract_answer_prefix(question: str, raw_answer: str) -> str:
    """Generate a concise prefix for better answer matching."""
    q_lower = question.lower().strip()
    a_lower = raw_answer.lower()

    if re.match(r"^(can |are |is |does |do |will |should )", q_lower):
        negatives = ["not ", "cannot ", "no ", "never ", "not allowed", "not counted"]
        if any(neg in a_lower for neg in negatives):
            return "No. "

    if "how many" in q_lower:
        unit_patterns = [
            (r"(\d+)\s+(working\s+days)", None),
            (r"(\d+)\s+(minutes)", None),
            (r"(\d+)\s+(semesters)", None),
            (r"(\d+)\s+(credits)", None),
            (r"(\d+)\s+(academic\s+years)", None),
            (r"(\d+)\s+(years)", None),
            (r"(\d+)\s+(days)", None),
            (r"(\d+)\s+(points)", None),
        ]
        for pat, _ in unit_patterns:
            m = re.search(pat, a_lower)
            if m:
                return f"{m.group(1)} {m.group(2)}. "

    return ""


def _build_answer_from_rows(rows: list[dict], question: str) -> str:
    """Synthesise a human-readable answer from KG query result rows."""
    if not rows:
        return "No matching regulation evidence found in KG."

    article_rows = [r for r in rows if r.get("source") == "article" and r.get("content")]
    rule_rows = [r for r in rows if r.get("source") == "rule" and r.get("action")]

    seen: set[str] = set()
    parts: list[str] = []

    for row in article_rows:
        content = row["content"].strip()
        if content not in seen:
            seen.add(content)
            parts.append(content)
        if len(parts) >= 3:
            break

    for row in rule_rows:
        action = (row.get("action") or "").strip()
        result = (row.get("result") or "").strip()
        if action and action not in seen and action != result:
            seen.add(action)
            parts.append(action)
        if result and result not in seen:
            seen.add(result)
            parts.append(result)
        if len(parts) >= 5:
            break

    if not parts:
        for row in rows:
            for key in ("content", "action", "result"):
                val = (row.get(key) or "").strip()
                if val and val not in seen:
                    seen.add(val)
                    parts.append(val)
            if parts:
                break

    raw = " ".join(parts) if parts else "No matching regulation evidence found in KG."

    prefix = _extract_answer_prefix(question, raw)
    if prefix:
        raw = prefix + raw

    return raw


def answer_question(question: str) -> dict[str, Any]:
    """
    Main entry point.
    Output contract for auto_test_a5.py:
    {
      "answer": str,
      "safety_decision": "ALLOW"|"REJECT",
      "diagnosis": "SUCCESS"|"QUERY_ERROR"|"SCHEMA_MISMATCH"|"NO_DATA",
      "repair_attempted": bool,
      "repair_changed": bool,
      "explanation": str
    }
    """
    nlu = PIPELINE["nlu"]
    security_agent = PIPELINE["security"]
    planner = PIPELINE["planner"]
    executor = PIPELINE["executor"]
    diagnosis_agent = PIPELINE["diagnosis"]
    repair_agent = PIPELINE["repair"]
    explanation_agent = PIPELINE["explanation"]

    intent = nlu.run(question)
    security = security_agent.run(question, intent)

    if security["decision"] == "REJECT":
        diagnosis = {"label": "QUERY_ERROR", "reason": "Blocked by policy."}
        answer = "Request rejected by security policy."
        explanation = explanation_agent.run(
            question, intent, security, diagnosis, answer, False
        )
        return {
            "answer": answer,
            "safety_decision": "REJECT",
            "diagnosis": diagnosis["label"],
            "repair_attempted": False,
            "repair_changed": False,
            "explanation": explanation,
        }

    plan = planner.run(intent)
    execution = executor.run(plan)
    diagnosis = diagnosis_agent.run(execution)

    repair_attempted = False
    repair_changed = False
    if diagnosis["label"] in {"QUERY_ERROR", "SCHEMA_MISMATCH", "NO_DATA"}:
        repair_attempted = True
        repaired_plan = repair_agent.run(diagnosis, plan, intent)
        repair_changed = repaired_plan != plan
        execution = executor.run(repaired_plan)
        diagnosis = diagnosis_agent.run(execution)

    if diagnosis["label"] == "SUCCESS":
        answer = _build_answer_from_rows(execution.get("rows", []), question)
    elif diagnosis["label"] == "NO_DATA":
        answer = "No matching regulation evidence found in KG."
    else:
        answer = "Query could not be resolved after repair attempt."

    explanation = explanation_agent.run(
        question, intent, security, diagnosis, answer, repair_attempted
    )
    return {
        "answer": answer,
        "safety_decision": "ALLOW",
        "diagnosis": diagnosis["label"],
        "repair_attempted": repair_attempted,
        "repair_changed": repair_changed,
        "explanation": explanation,
    }


def run_multiagent_qa(question: str) -> dict[str, Any]:
    return answer_question(question)


if __name__ == "__main__":
    while True:
        q = input("Question (type exit): ").strip()
        if not q or q.lower() in {"exit", "quit"}:
            break
        result = answer_question(q)
        print(f"Answer: {result['answer']}")
        print(f"Safety: {result['safety_decision']}")
        print(f"Diagnosis: {result['diagnosis']}")
        print(f"Repair: attempted={result['repair_attempted']}, changed={result['repair_changed']}")
        print()
