from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "i", "me", "my",
    "you", "your", "he", "she", "it", "we", "they", "them", "their",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "how", "when", "where", "why", "if", "or", "and", "but", "not",
    "no", "nor", "so", "too", "very", "just", "about", "above", "after",
    "again", "all", "also", "am", "any", "at", "before", "below",
    "between", "both", "by", "during", "each", "few", "for", "from",
    "further", "get", "got", "here", "in", "into", "more", "most",
    "of", "off", "on", "once", "only", "other", "our", "out", "over",
    "own", "same", "some", "such", "than", "then", "there", "through",
    "to", "under", "until", "up", "with", "down", "like", "probably",
    "generally", "maybe", "perhaps", "right", "okay", "fine", "bit",
    "really", "heard", "tell", "told", "know", "think", "sure",
})


@dataclass
class Intent:
    question_type: str
    keywords: list[str]
    aspect: str
    ambiguous: bool = False
    raw_question: str = ""


class NLUnderstandingAgent:
    def run(self, question: str) -> Intent:
        q_lower = question.lower().strip()
        tokens = re.findall(r"[a-z0-9]+", q_lower)
        keywords = [t for t in tokens if t not in STOPWORDS and len(t) > 1]

        question_type = "general"
        aspect = "general"

        if any(w in q_lower for w in ["late", "barred", "arriving"]):
            question_type = "exam_timing"
            aspect = "exam_late"
        elif any(w in q_lower for w in ["leave", "early", "depart"]) and "exam" in q_lower:
            question_type = "exam_timing"
            aspect = "exam_leave_early"
        elif any(w in q_lower for w in ["cheat", "copy", "passing notes", "dishonest"]):
            question_type = "penalty"
            aspect = "cheating"
        elif any(w in q_lower for w in ["threaten", "insult", "confront", "invigilator"]):
            question_type = "penalty"
            aspect = "threatening"
        elif any(w in q_lower for w in ["question paper", "take.*paper", "paper out"]):
            question_type = "penalty"
            aspect = "question_paper"
        elif any(w in q_lower for w in ["electronic", "phone", "device", "communication"]):
            question_type = "penalty"
            aspect = "electronic_devices"
        elif "student id" in q_lower or "id card" in q_lower or "forgetting" in q_lower:
            if any(w in q_lower for w in ["fee", "cost", "replacing", "replace", "lost"]):
                question_type = "fee"
                aspect = "id_replacement_fee"
            elif any(w in q_lower for w in ["penalty", "forget", "forgetting"]):
                question_type = "penalty"
                aspect = "forgetting_id"
            elif "working days" in q_lower or "how long" in q_lower or "days" in q_lower:
                question_type = "duration"
                aspect = "id_processing_time"
            else:
                question_type = "general"
                aspect = "student_id"
        elif "easycard" in q_lower:
            question_type = "fee"
            aspect = "easycard_fee"
        elif "mifare" in q_lower:
            question_type = "fee"
            aspect = "mifare_fee"
        elif any(w in q_lower for w in ["credit", "graduation"]) and any(w in q_lower for w in ["minimum", "total", "require"]):
            question_type = "requirement"
            aspect = "graduation_credits"
        elif "physical education" in q_lower or ("pe " in q_lower and "semester" in q_lower):
            question_type = "requirement"
            aspect = "pe_requirement"
        elif "military" in q_lower:
            question_type = "requirement"
            aspect = "military_training"
        elif "passing score" in q_lower or "pass" in q_lower and "score" in q_lower:
            if any(w in q_lower for w in ["graduate", "master", "phd"]):
                question_type = "grade"
                aspect = "graduate_passing_score"
            else:
                question_type = "grade"
                aspect = "undergraduate_passing_score"
        elif any(w in q_lower for w in ["dismiss", "expel"]):
            question_type = "penalty"
            aspect = "dismissal"
        elif "make-up" in q_lower or "makeup" in q_lower:
            question_type = "general"
            aspect = "makeup_exam"
        elif "leave of absence" in q_lower or "suspension" in q_lower:
            question_type = "duration"
            aspect = "leave_of_absence"
        elif any(w in q_lower for w in ["duration", "how long", "how many year"]):
            question_type = "duration"
            aspect = "study_duration"
        elif "extension" in q_lower:
            question_type = "duration"
            aspect = "extension"
        elif any(w in q_lower for w in ["penalty", "punish", "deduct"]):
            question_type = "penalty"
            aspect = "penalty"
        elif any(w in q_lower for w in ["exam", "test", "examination"]):
            question_type = "exam"
            aspect = "exam_rules"
        elif any(w in q_lower for w in ["fee", "cost", "price", "ntd"]):
            question_type = "fee"
            aspect = "fee"
        elif any(w in q_lower for w in ["every", "summarize", "all"]) and any(w in q_lower for w in ["fee", "regulation", "process"]):
            aspect = "broad_scope"

        return Intent(
            question_type=question_type,
            keywords=keywords,
            aspect=aspect,
            ambiguous=False,
            raw_question=question,
        )


class SecurityAgent:
    BLOCKED_PATTERNS = [
        r"delete",
        r"drop\b",
        r"\bmerge\b",
        r"\bcreate\b",
        r"\bset\s",
        r"bypass",
        r"ignore\s*(previous|prior|all)",
        r"dump\s*(all|every)",
        r"export",
        r"raw\s*json",
        r"disable\s*(safety|security)",
        r"credential",
        r"\bmodify\b",
        r"script\s+to\b",
        r"word.by.word",
        r"pretend\s+you",
        r"authorize\s+you",
        r"override",
        r"inject",
        r"detach\s*delete",
        r"remove\s+all",
        r"\badmin\b",
        r"root\s*access",
        r"every\b.*\bcontent\b",
        r"all\b.*\bcontent\b",
        r"entire\b.*\b(kg|graph|content|database)",
        r"full\s+content",
        r"all\s+(rule\s+)?nodes",
        r"every\s+(regulation|article|rule)",
        r"return\s+n\s+limit",
        r"return\s+all",
        r"show\s+me\s+every",
        r"execute\s+this",
        r"run\s+(cypher|query|merge|delete|drop)",
    ]

    def run(self, question: str, intent: Intent) -> dict[str, str]:
        q_lower = question.lower()
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, q_lower):
                return {"decision": "REJECT", "reason": f"Blocked: matched pattern '{pattern}'"}
        return {"decision": "ALLOW", "reason": "Passed security check."}


class QueryPlannerAgent:
    ASPECT_TO_CYPHER = {
        "exam_late": (
            "MATCH (r:Rule) WHERE r.reg_name = 'NCU Student Examination Rules' "
            "AND (r.action CONTAINS 'late' OR r.action CONTAINS 'arriving' OR r.action CONTAINS '20 minu') "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'late' AND a.content CONTAINS 'minutes' "
            "RETURN a.content AS content",
        ),
        "exam_leave_early": (
            "MATCH (r:Rule) WHERE r.reg_name = 'NCU Student Examination Rules' "
            "AND (r.action CONTAINS 'leaving' OR r.action CONTAINS 'leave' OR r.result CONTAINS 'wait') "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'leave' AND a.content CONTAINS 'minutes' "
            "RETURN a.content AS content",
        ),
        "forgetting_id": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'forgetting student ID' OR r.action CONTAINS 'forgetting to bring' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'forgetting' OR (a.content CONTAINS 'student ID' AND a.content CONTAINS 'penalty') "
            "RETURN a.content AS content",
        ),
        "electronic_devices": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'electronic' OR r.action CONTAINS 'device' OR r.action CONTAINS 'phone' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'Electronic' OR a.content CONTAINS 'device' "
            "RETURN a.content AS content",
        ),
        "cheating": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'cheat' OR r.action CONTAINS 'copying' OR r.action CONTAINS 'dishonest' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'Cheating' OR a.content CONTAINS 'copying' "
            "RETURN a.content AS content",
        ),
        "question_paper": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'question paper' OR r.action CONTAINS 'paper out' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'question paper' "
            "RETURN a.content AS content",
        ),
        "threatening": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'threaten' OR r.action CONTAINS 'insult' OR r.action CONTAINS 'invigilator' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'threatens' OR a.content CONTAINS 'invigilator' "
            "RETURN a.content AS content",
        ),
        "easycard_fee": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'EasyCard' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'EasyCard' "
            "RETURN a.content AS content",
        ),
        "id_replacement_fee": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'EasyCard' OR r.action CONTAINS 'Mifare' OR r.action CONTAINS 'replacing' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'EasyCard' OR a.content CONTAINS 'Mifare' OR a.content CONTAINS 'fee' "
            "RETURN a.content AS content",
        ),
        "mifare_fee": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'Mifare' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'Mifare' "
            "RETURN a.content AS content",
        ),
        "id_processing_time": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'working days' OR r.action CONTAINS 'ID card processing' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'working days' "
            "RETURN a.content AS content",
        ),
        "graduation_credits": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'graduation' AND r.action CONTAINS 'credit' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'credits' AND a.content CONTAINS 'graduation' "
            "RETURN a.content AS content",
        ),
        "pe_requirement": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'PE' OR r.action CONTAINS 'Physical Education' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'Physical Education' OR a.content CONTAINS 'PE' "
            "RETURN a.content AS content",
        ),
        "military_training": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'military' OR r.action CONTAINS 'Military' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'Military' "
            "RETURN a.content AS content",
        ),
        "undergraduate_passing_score": (
            "MATCH (r:Rule) WHERE r.type = 'grade' AND r.action CONTAINS 'undergraduate' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'passing score' AND a.content CONTAINS 'undergraduate' "
            "RETURN a.content AS content",
        ),
        "graduate_passing_score": (
            "MATCH (r:Rule) WHERE r.type = 'grade' AND (r.action CONTAINS 'graduate' OR r.action CONTAINS 'Master' OR r.action CONTAINS 'PhD') "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'passing score' AND a.content CONTAINS 'graduate' "
            "RETURN a.content AS content",
        ),
        "dismissal": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'dismiss' OR r.action CONTAINS 'expel' OR r.action CONTAINS 'failing' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'dismissed' OR a.content CONTAINS 'expelled' "
            "RETURN a.content AS content",
        ),
        "makeup_exam": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'make-up' OR r.action CONTAINS 'makeup' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'make-up' "
            "RETURN a.content AS content",
        ),
        "leave_of_absence": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'leave of absence' OR r.action CONTAINS 'suspension' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'leave of absence' OR a.content CONTAINS 'suspension' "
            "RETURN a.content AS content",
        ),
        "study_duration": (
            "MATCH (r:Rule) WHERE r.type = 'duration' AND (r.action CONTAINS 'bachelor' OR r.action CONTAINS 'standard') "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'duration' AND a.content CONTAINS 'bachelor' "
            "RETURN a.content AS content",
        ),
        "extension": (
            "MATCH (r:Rule) WHERE r.action CONTAINS 'extension' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'extension' "
            "RETURN a.content AS content",
        ),
        "student_id": (
            "MATCH (r:Rule) WHERE r.reg_name = 'Student ID Card Replacement Rules' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, r.art_ref AS art_ref, r.reg_name AS reg_name",
            "MATCH (a:Article) WHERE a.content CONTAINS 'student ID' "
            "RETURN a.content AS content",
        ),
    }

    def run(self, intent: Intent) -> dict[str, Any]:
        keywords = intent.keywords
        search_terms = " ".join(keywords)

        if intent.aspect in self.ASPECT_TO_CYPHER:
            rule_q, article_q = self.ASPECT_TO_CYPHER[intent.aspect]
        else:
            rule_q = (
                "CALL db.index.fulltext.queryNodes('rule_idx', $search_terms) "
                "YIELD node, score "
                "RETURN node.action AS action, node.result AS result, "
                "node.type AS type, node.art_ref AS art_ref, "
                "node.reg_name AS reg_name, score "
                "ORDER BY score DESC LIMIT 10"
            )
            article_q = (
                "CALL db.index.fulltext.queryNodes('article_content_idx', $search_terms) "
                "YIELD node, score "
                "RETURN node.content AS content, score "
                "ORDER BY score DESC LIMIT 5"
            )

        return {
            "strategy": "aspect_targeted" if intent.aspect in self.ASPECT_TO_CYPHER else "fulltext_combined",
            "keywords": keywords,
            "search_terms": search_terms,
            "aspect": intent.aspect,
            "rule_query": rule_q,
            "article_query": article_q,
        }


class QueryExecutionAgent:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        pwd = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(uri, auth=(user, pwd))

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        search_terms = plan.get("search_terms", "")
        rows: list[dict] = []

        try:
            with self.driver.session() as session:
                rule_q = plan.get("rule_query", "")
                if rule_q:
                    if "$search_terms" in rule_q:
                        if not search_terms.strip():
                            pass
                        else:
                            result = session.run(rule_q, search_terms=search_terms)
                            for rec in result:
                                rows.append({
                                    "source": "rule",
                                    "action": rec.get("action"),
                                    "result": rec.get("result"),
                                    "type": rec.get("type"),
                                    "art_ref": rec.get("art_ref"),
                                    "reg_name": rec.get("reg_name"),
                                    "score": rec.get("score", 1.0),
                                })
                    else:
                        result = session.run(rule_q)
                        for rec in result:
                            rows.append({
                                "source": "rule",
                                "action": rec.get("action"),
                                "result": rec.get("result"),
                                "type": rec.get("type"),
                                "art_ref": rec.get("art_ref"),
                                "reg_name": rec.get("reg_name"),
                                "score": 1.0,
                            })

                article_q = plan.get("article_query", "")
                if article_q:
                    if "$search_terms" in article_q:
                        if not search_terms.strip():
                            pass
                        else:
                            result = session.run(article_q, search_terms=search_terms)
                            for rec in result:
                                rows.append({
                                    "source": "article",
                                    "content": rec.get("content"),
                                    "score": rec.get("score", 1.0),
                                })
                    else:
                        result = session.run(article_q)
                        for rec in result:
                            rows.append({
                                "source": "article",
                                "content": rec.get("content"),
                                "score": 1.0,
                            })

            return {"rows": rows, "error": None}
        except Exception as e:
            return {"rows": [], "error": str(e)}


class DiagnosisAgent:
    def run(self, execution: dict[str, Any]) -> dict[str, str]:
        error = execution.get("error")
        if error:
            err_lower = str(error).lower()
            if "schema" in err_lower or "index" in err_lower or "no such" in err_lower:
                return {"label": "SCHEMA_MISMATCH", "reason": str(error)}
            return {"label": "QUERY_ERROR", "reason": str(error)}
        if not execution.get("rows"):
            return {"label": "NO_DATA", "reason": "No matching data found in KG."}
        return {"label": "SUCCESS", "reason": "Query returned results."}


class QueryRepairAgent:
    ASPECT_FALLBACK = {
        "exam_rules": (
            "MATCH (r:Rule) WHERE r.reg_name = 'NCU Student Examination Rules' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, "
            "r.art_ref AS art_ref, r.reg_name AS reg_name LIMIT 10",
            "MATCH (a:Article) WHERE a.content CONTAINS 'exam' "
            "RETURN a.content AS content LIMIT 5",
        ),
        "exam_timing": (
            "MATCH (r:Rule) WHERE r.reg_name = 'NCU Student Examination Rules' "
            "AND r.type IN ['exam_timing', 'penalty'] "
            "RETURN r.action AS action, r.result AS result, r.type AS type, "
            "r.art_ref AS art_ref, r.reg_name AS reg_name LIMIT 10",
            "MATCH (a:Article) WHERE a.content CONTAINS 'exam' "
            "RETURN a.content AS content LIMIT 5",
        ),
        "penalty": (
            "MATCH (r:Rule) WHERE r.type = 'penalty' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, "
            "r.art_ref AS art_ref, r.reg_name AS reg_name LIMIT 10",
            "MATCH (a:Article) WHERE a.content CONTAINS 'penalty' OR a.content CONTAINS 'zero' "
            "RETURN a.content AS content LIMIT 5",
        ),
        "fee": (
            "MATCH (r:Rule) WHERE r.reg_name = 'Student ID Card Replacement Rules' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, "
            "r.art_ref AS art_ref, r.reg_name AS reg_name LIMIT 10",
            "MATCH (a:Article) WHERE a.content CONTAINS 'fee' OR a.content CONTAINS 'NTD' "
            "RETURN a.content AS content LIMIT 5",
        ),
        "student_id": (
            "MATCH (r:Rule) WHERE r.reg_name = 'Student ID Card Replacement Rules' "
            "RETURN r.action AS action, r.result AS result, r.type AS type, "
            "r.art_ref AS art_ref, r.reg_name AS reg_name LIMIT 10",
            "MATCH (a:Article) WHERE a.content CONTAINS 'student ID' "
            "RETURN a.content AS content LIMIT 5",
        ),
        "broad_scope": (
            "MATCH (r:Rule) WHERE r.type IN ['general', 'duration', 'requirement'] "
            "RETURN r.action AS action, r.result AS result, r.type AS type, "
            "r.art_ref AS art_ref, r.reg_name AS reg_name LIMIT 10",
            "MATCH (a:Article) RETURN a.content AS content LIMIT 5",
        ),
    }

    KEYWORD_SYNONYMS = {
        "test": "exam",
        "tests": "exam",
        "card": "student ID",
        "punishment": "penalty",
        "expelled": "dismissed",
        "phone": "electronic devices",
    }

    def run(
        self,
        diagnosis: dict[str, str],
        original_plan: dict[str, Any],
        intent: Intent,
    ) -> dict[str, Any]:
        repaired = dict(original_plan)
        repaired["strategy"] = "repair_broad"

        if intent.aspect in self.ASPECT_FALLBACK:
            rule_q, art_q = self.ASPECT_FALLBACK[intent.aspect]
            repaired["rule_query"] = rule_q
            repaired["article_query"] = art_q
            return repaired

        keywords = intent.keywords
        expanded = []
        for kw in keywords:
            expanded.append(kw)
            if kw in self.KEYWORD_SYNONYMS:
                expanded.append(self.KEYWORD_SYNONYMS[kw])
            if len(kw) > 4:
                expanded.append(kw + "~")

        repaired["search_terms"] = " ".join(expanded) if expanded else " ".join(keywords)
        repaired["rule_query"] = (
            "CALL db.index.fulltext.queryNodes('rule_idx', $search_terms) "
            "YIELD node, score "
            "RETURN node.action AS action, node.result AS result, "
            "node.type AS type, node.art_ref AS art_ref, "
            "node.reg_name AS reg_name, score "
            "ORDER BY score DESC LIMIT 10"
        )
        repaired["article_query"] = (
            "CALL db.index.fulltext.queryNodes('article_content_idx', $search_terms) "
            "YIELD node, score "
            "RETURN node.content AS content, score "
            "ORDER BY score DESC LIMIT 5"
        )
        return repaired


class ExplanationAgent:
    def run(
        self,
        question: str,
        intent: Intent,
        security: dict[str, str],
        diagnosis: dict[str, str],
        answer: str,
        repair_attempted: bool,
    ) -> str:
        parts = [
            f"Intent={intent.question_type}",
            f"Security={security['decision']}",
            f"Diagnosis={diagnosis['label']}",
        ]
        if repair_attempted:
            parts.append("Repair=attempted")
        parts.append(f"Answer: {answer}")
        return " | ".join(parts)


def build_template_pipeline() -> dict[str, Any]:
    return {
        "nlu": NLUnderstandingAgent(),
        "security": SecurityAgent(),
        "planner": QueryPlannerAgent(),
        "executor": QueryExecutionAgent(),
        "diagnosis": DiagnosisAgent(),
        "repair": QueryRepairAgent(),
        "explanation": ExplanationAgent(),
    }
