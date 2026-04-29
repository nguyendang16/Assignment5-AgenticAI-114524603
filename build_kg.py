"""Minimal KG builder template for Assignment 4.

Keep this contract unchanged:
- Graph: (Regulation)-[:HAS_ARTICLE]->(Article)-[:CONTAINS_RULE]->(Rule)
- Article: number, content, reg_name, category
- Rule: rule_id, type, action, result, art_ref, reg_name
- Fulltext indexes: article_content_idx, rule_idx
- SQLite file: ncu_regulations.db
"""

import os
import re
import json
import sqlite3
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

from llm_loader import load_local_llm, get_tokenizer, get_raw_pipeline


# ========== 0) Initialization ==========
load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (
    os.getenv("NEO4J_USER", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "password"),
)


def extract_entities(article_number: str, reg_name: str, content: str) -> dict[str, Any]:
    """Use LLM to extract rules from article content, with fallback for reliability."""
    tok = get_tokenizer()
    pipe = get_raw_pipeline()
    if tok is None or pipe is None:
        load_local_llm()
        tok = get_tokenizer()
        pipe = get_raw_pipeline()

    prompt_text = f"""Extract rules from this university regulation article. Return a JSON object with a "rules" array.

Each rule should have:
- "type": category (e.g., "penalty", "requirement", "procedure", "fee", "duration", "prohibition", "permission")
- "action": the condition or trigger (e.g., "late more than 20 minutes", "cheating", "forgetting student ID")
- "result": the consequence or value (e.g., "barred from exam", "zero score", "5 points deduction", "200 NTD")

Article: {article_number}
Regulation: {reg_name}
Content: {content}

Return ONLY valid JSON. Example: {{"rules": [{{"type": "penalty", "action": "cheating", "result": "zero score"}}]}}
If no clear rules found, return: {{"rules": []}}

JSON:"""

    messages = [
        {"role": "system", "content": "You extract structured rules from regulation text. Return only valid JSON, no explanation."},
        {"role": "user", "content": prompt_text}
    ]

    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    output = pipe(prompt, max_new_tokens=400)[0]["generated_text"].strip()

    llm_rules = []
    # Parse JSON from LLM output
    try:
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            if "rules" in result and isinstance(result["rules"], list):
                llm_rules = result["rules"]
    except (json.JSONDecodeError, AttributeError):
        pass

    # Always get fallback rules for better coverage
    fallback_rules = build_fallback_rules(article_number, content)

    # Merge LLM rules with fallback rules (LLM rules take priority)
    all_rules = llm_rules.copy()
    seen_actions = set(r.get("action", "")[:50].lower() for r in llm_rules if r.get("action"))
    
    for fb_rule in fallback_rules:
        action_key = fb_rule.get("action", "")[:50].lower()
        if action_key and action_key not in seen_actions:
            all_rules.append(fb_rule)
            seen_actions.add(action_key)

    return {"rules": all_rules}


def build_fallback_rules(article_number: str, content: str) -> list[dict[str, str]]:
    """Deterministic rules extraction based on regex patterns."""
    rules = []
    content_lower = content.lower()

    # Exam-related rules (ncu6.pdf)
    exam_rules = [
        # Late arrival
        (r'(?:late|tardy|arrive).*?(\d+)\s*minutes?.*?(?:barred|not.*?(?:allowed|permitted)|denied)', 
         'exam_timing', 'arriving late to exam', 'barred from exam after time limit'),
        (r'(\d+)\s*minutes?.*?late.*?(?:barred|not allowed|denied|cannot)',
         'exam_timing', 'arriving more than X minutes late', 'barred from exam'),
        # Early leaving
        (r'(?:leave|exit|depart).*?(?:after|within).*?(\d+)\s*minutes?',
         'exam_timing', 'leaving exam early', 'must wait specified time before leaving'),
        (r'(\d+)\s*minutes?.*?(?:may|can|allowed).*?(?:leave|exit)',
         'exam_timing', 'early exam departure', 'can leave after specified time'),
        # Point deductions
        (r'(\d+)\s*points?\s*(?:will be\s*)?(?:deduct|subtract)',
         'penalty', 'violation', 'points deducted'),
        (r'deduct(?:ed|ion)?\s*(?:of\s*)?(\d+)\s*points?',
         'penalty', 'violation', 'points deducted'),
        # Zero score penalties
        (r'(?:zero|0)\s*(?:score|mark|grade|point)',
         'penalty', 'serious violation', 'zero score'),
        (r'score.*?(?:shall|will|be)\s*(?:zero|0)',
         'penalty', 'serious violation', 'zero score'),
        # Cheating
        (r'cheat(?:ing)?.*?(?:zero|disciplinary|punishment)',
         'penalty', 'cheating during exam', 'zero score and/or disciplinary action'),
        (r'copy(?:ing)?.*?(?:zero|disciplinary|punishment)',
         'penalty', 'copying during exam', 'zero score and/or disciplinary action'),
        # Threatening behavior
        (r'threaten(?:ing)?.*?(?:invigilator|proctor|supervisor)',
         'penalty', 'threatening invigilator', 'zero score and disciplinary action'),
        # Question paper
        (r'(?:question\s*paper|exam\s*paper).*?(?:take|remove|out)',
         'penalty', 'taking question paper out', 'zero score'),
        # Electronic devices
        (r'(?:electronic|device|phone|mobile|communication).*?(?:deduct|penalty|punish)',
         'penalty', 'using electronic devices', 'points deduction or zero score'),
        # Student ID
        (r'(?:forget|forgot|without).*?(?:student\s*id|id\s*card).*?(\d+)\s*points?',
         'penalty', 'forgetting student ID', 'points deducted'),
        (r'(?:student\s*id|id\s*card).*?(?:forget|forgot|without).*?(\d+)\s*points?',
         'penalty', 'forgetting student ID', 'points deducted'),
    ]

    # ID card replacement rules (ncu5.pdf)
    id_rules = [
        (r'(?:easycard|easy\s*card).*?(?:NT\$?|NTD)\s*(\d+)',
         'fee', 'EasyCard student ID replacement', 'fee amount'),
        (r'(?:NT\$?|NTD)\s*(\d+).*?(?:easycard|easy\s*card)',
         'fee', 'EasyCard student ID replacement', 'fee amount'),
        (r'(?:mifare|non-easycard).*?(?:NT\$?|NTD)\s*(\d+)',
         'fee', 'Mifare student ID replacement', 'fee amount'),
        (r'(?:NT\$?|NTD)\s*(\d+).*?(?:mifare|non-easycard)',
         'fee', 'Mifare student ID replacement', 'fee amount'),
        (r'(\d+)\s*(?:working)?\s*days?.*?(?:new|replacement|issue)',
         'duration', 'ID card processing', 'working days to receive'),
        (r'(?:replacement|new).*?(\d+)\s*(?:working)?\s*days?',
         'duration', 'ID card processing', 'working days to receive'),
    ]

    # Academic rules (ncu1.pdf)
    academic_rules = [
        # Credits
        (r'(\d+)\s*credits?.*?(?:graduate|graduation|minimum|required|total)',
         'requirement', 'graduation credits', 'minimum credits required'),
        (r'(?:graduate|graduation|minimum|required|total).*?(\d+)\s*credits?',
         'requirement', 'graduation credits', 'minimum credits required'),
        # PE/Physical Education
        (r'(\d+)\s*semesters?.*?(?:pe|physical\s*education)',
         'requirement', 'PE requirement', 'semesters of PE required'),
        (r'(?:pe|physical\s*education).*?(\d+)\s*semesters?',
         'requirement', 'PE requirement', 'semesters of PE required'),
        # Military training
        (r'military.*?(?:not|do not|shall not).*?(?:count|include|toward)',
         'requirement', 'military training credits', 'not counted toward graduation'),
        # Study duration - standard
        (r'standard\s*duration.*?(\d+)\s*years?',
         'duration', 'bachelor degree duration', 'standard study period'),
        (r'(\d+)\s*years?.*?standard\s*duration',
         'duration', 'bachelor degree duration', 'standard study period'),
        (r"bachelor'?s?\s*degree.*?(\d+)\s*years?",
         'duration', 'bachelor degree duration', 'standard study period'),
        # Extension - maximum period
        (r'maximum\s*extension.*?(\d+)\s*years?',
         'duration', 'study extension', 'maximum extension period'),
        (r'extension\s*period.*?(\d+)\s*years?',
         'duration', 'study extension', 'maximum extension period'),
        (r'(\d+)\s*years?\s*(?:beyond|extension)',
         'duration', 'study extension', 'maximum extension period'),
        # Passing scores - undergraduate specific
        (r'passing\s*score.*?undergraduate.*?(\d+)\s*points?',
         'grade', 'undergraduate passing score', 'minimum score to pass'),
        (r'undergraduate.*?passing\s*score.*?(\d+)\s*points?',
         'grade', 'undergraduate passing score', 'minimum score to pass'),
        (r'passing\s*score.*?(\d+)\s*points?.*?undergraduate',
         'grade', 'undergraduate passing score', 'minimum score to pass'),
        # Passing scores - graduate specific
        (r'passing\s*score.*?graduate.*?(\d+)\s*points?',
         'grade', 'graduate passing score', 'minimum score to pass'),
        (r'graduate.*?passing\s*score.*?(\d+)\s*points?',
         'grade', 'graduate passing score', 'minimum score to pass'),
        (r'passing\s*score.*?(\d+)\s*points?.*?(?:master|phd|graduate)',
         'grade', 'graduate passing score', 'minimum score to pass'),
        # Dismissal - failing credits
        (r'dismiss(?:ed)?.*?fail.*?(?:more than\s*)?half',
         'penalty', 'failing too many credits', 'dismissal from university'),
        (r'fail.*?(?:more than\s*)?half.*?dismiss(?:ed)?',
         'penalty', 'failing too many credits', 'dismissal from university'),
        (r'dismiss(?:ed)?.*?(?:1/2|50%|half).*?credits?',
         'penalty', 'failing too many credits', 'dismissal from university'),
        (r'(?:1/2|50%|half).*?credits?.*?dismiss(?:ed)?',
         'penalty', 'failing too many credits', 'dismissal from university'),
        (r'expelled.*?fail',
         'penalty', 'failing too many credits', 'dismissal from university'),
        # Make-up exam
        (r'cannot\s*take.*?make-?up\s*exam',
         'prohibition', 'make-up exam for failed courses', 'not allowed'),
        (r'make-?up\s*exam.*?(?:not|cannot)',
         'prohibition', 'make-up exam for failed courses', 'not allowed'),
        # Leave of absence
        (r'leave\s*of\s*absence.*?(\d+)\s*(?:academic\s*)?years?',
         'duration', 'leave of absence', 'maximum allowed period'),
        (r'suspension.*?schooling.*?(\d+)\s*(?:academic\s*)?years?',
         'duration', 'leave of absence', 'maximum allowed period'),
        (r'(\d+)\s*(?:academic\s*)?years?.*?leave\s*of\s*absence',
         'duration', 'leave of absence', 'maximum allowed period'),
    ]

    # Process all rule patterns
    all_patterns = exam_rules + id_rules + academic_rules
    
    for pattern, rule_type, action_desc, result_desc in all_patterns:
        match = re.search(pattern, content_lower)
        if match:
            # Try to extract the specific number/value
            groups = match.groups()
            value = groups[0] if groups else ""
            
            full_match = match.group(0)
            rules.append({
                "type": rule_type,
                "action": f"{action_desc}: {full_match[:80]}",
                "result": f"{result_desc}: {value}" if value else result_desc
            })

    # Additional specific number extractions
    # Fee amounts
    fee_match = re.search(r'(?:NT\$?|NTD)\s*(\d+)', content, re.IGNORECASE)
    if fee_match and not any(r["type"] == "fee" for r in rules):
        rules.append({
            "type": "fee",
            "action": content[:100],
            "result": f"NT${fee_match.group(1)}"
        })

    # Credit amounts
    credit_match = re.search(r'(\d+)\s*credits?', content_lower)
    if credit_match and not any("credit" in r.get("type", "") for r in rules):
        rules.append({
            "type": "credit_requirement",
            "action": content[:100],
            "result": f"{credit_match.group(1)} credits"
        })

    # Point deductions
    deduct_match = re.search(r'(\d+)\s*points?', content_lower)
    if deduct_match and "deduct" in content_lower and not any("points" in r.get("result", "") for r in rules):
        rules.append({
            "type": "penalty",
            "action": content[:100],
            "result": f"{deduct_match.group(1)} points deduction"
        })

    # If no specific rules found, create a general rule with the content
    if not rules and len(content) > 20:
        rules.append({
            "type": "general",
            "action": content[:200] if len(content) > 200 else content,
            "result": content[:200] if len(content) > 200 else content
        })

    return rules


# SQLite tables used:
# - regulations(reg_id, name, category)
# - articles(reg_id, article_number, content)


def build_graph() -> None:
    """Build KG from SQLite into Neo4j using the fixed assignment schema."""
    sql_conn = sqlite3.connect("ncu_regulations.db")
    cursor = sql_conn.cursor()
    driver = GraphDatabase.driver(URI, auth=AUTH)

    # Load LLM for rule extraction
    print("[*] Loading LLM for rule extraction...")
    load_local_llm()

    with driver.session() as session:
        # Fixed strategy: clear existing graph data before rebuilding.
        session.run("MATCH (n) DETACH DELETE n")

        # 1) Read regulations and create Regulation nodes.
        cursor.execute("SELECT reg_id, name, category FROM regulations")
        regulations = cursor.fetchall()
        reg_map: dict[int, tuple[str, str]] = {}

        for reg_id, name, category in regulations:
            reg_map[reg_id] = (name, category)
            session.run(
                "MERGE (r:Regulation {id:$rid}) SET r.name=$name, r.category=$cat",
                rid=reg_id,
                name=name,
                cat=category,
            )

        # 2) Read articles and create Article + HAS_ARTICLE.
        cursor.execute("SELECT reg_id, article_number, content FROM articles")
        articles = cursor.fetchall()

        for reg_id, article_number, content in articles:
            reg_name, reg_category = reg_map.get(reg_id, ("Unknown", "Unknown"))
            session.run(
                """
                MATCH (r:Regulation {id: $rid})
                CREATE (a:Article {
                    number:   $num,
                    content:  $content,
                    reg_name: $reg_name,
                    category: $reg_category
                })
                MERGE (r)-[:HAS_ARTICLE]->(a)
                """,
                rid=reg_id,
                num=article_number,
                content=content,
                reg_name=reg_name,
                reg_category=reg_category,
            )

        # 3) Create full-text index on Article content.
        session.run(
            """
            CREATE FULLTEXT INDEX article_content_idx IF NOT EXISTS
            FOR (a:Article) ON EACH [a.content]
            """
        )

        rule_counter = 0
        seen_rules = set()  # For deduplication

        # Iterate through all articles and extract rules
        for reg_id, article_number, content in articles:
            reg_name, reg_category = reg_map.get(reg_id, ("Unknown", "Unknown"))

            print(f"  Processing: {reg_name} - {article_number}")
            extracted = extract_entities(article_number, reg_name, content)
            rules = extracted.get("rules", [])

            for rule in rules:
                action = rule.get("action", "").strip()
                result = rule.get("result", "").strip()
                rule_type = rule.get("type", "general").strip()

                # Skip invalid rules with empty action/result
                if not action or not result:
                    continue

                # Deduplication based on action+result hash
                rule_hash = f"{action[:50]}|{result[:50]}|{article_number}"
                if rule_hash in seen_rules:
                    continue
                seen_rules.add(rule_hash)

                rule_counter += 1
                rule_id = f"R{rule_counter:04d}"

                # Create Rule node and link to Article
                session.run(
                    """
                    MATCH (a:Article {number: $art_num, reg_name: $reg_name})
                    CREATE (rule:Rule {
                        rule_id: $rule_id,
                        type: $type,
                        action: $action,
                        result: $result,
                        art_ref: $art_ref,
                        reg_name: $reg_name
                    })
                    MERGE (a)-[:CONTAINS_RULE]->(rule)
                    """,
                    art_num=article_number,
                    reg_name=reg_name,
                    rule_id=rule_id,
                    type=rule_type,
                    action=action,
                    result=result,
                    art_ref=article_number,
                )

        print(f"[Rules] Created {rule_counter} Rule nodes.")

        # 4) Create full-text index on Rule fields.
        session.run(
            """
            CREATE FULLTEXT INDEX rule_idx IF NOT EXISTS
            FOR (r:Rule) ON EACH [r.action, r.result]
            """
        )

        # 5) Coverage audit (provided scaffold).
        coverage = session.run(
            """
            MATCH (a:Article)
            OPTIONAL MATCH (a)-[:CONTAINS_RULE]->(r:Rule)
            WITH a, count(r) AS rule_count
            RETURN count(a) AS total_articles,
                   sum(CASE WHEN rule_count > 0 THEN 1 ELSE 0 END) AS covered_articles,
                   sum(CASE WHEN rule_count = 0 THEN 1 ELSE 0 END) AS uncovered_articles
            """
        ).single()

        total_articles = int((coverage or {}).get("total_articles", 0) or 0)
        covered_articles = int((coverage or {}).get("covered_articles", 0) or 0)
        uncovered_articles = int((coverage or {}).get("uncovered_articles", 0) or 0)

        print(
            f"[Coverage] covered={covered_articles}/{total_articles}, "
            f"uncovered={uncovered_articles}"
        )

    driver.close()
    sql_conn.close()


if __name__ == "__main__":
    build_graph()
