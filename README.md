# Assignment 5: KG Multi-Agent QA System

## Architecture Overview

```
Question
   │
   ▼
┌─────────────────────┐
│  NL Understanding   │  Extract keywords, classify question type & aspect
│  Agent              │
└────────┬────────────┘
         │ Intent
         ▼
┌─────────────────────┐
│  Security / Policy  │  Pattern-based blocklist for unsafe queries
│  Agent              │──── REJECT ──→ Early return
└────────┬────────────┘
         │ ALLOW
         ▼
┌─────────────────────┐
│  Query Planner      │  Aspect-targeted Cypher or fulltext fallback
│  Agent              │
└────────┬────────────┘
         │ Plan (Cypher queries)
         ▼
┌─────────────────────┐
│  Query Execution    │  Execute against Neo4j (read-only)
│  Agent              │
└────────┬────────────┘
         │ Rows / Error
         ▼
┌─────────────────────┐
│  Diagnosis          │  SUCCESS / QUERY_ERROR / SCHEMA_MISMATCH / NO_DATA
│  Agent              │
└────────┬────────────┘
         │
    ┌────┴─────────────┐
    │ ERROR / NO_DATA  │ SUCCESS
    ▼                  ▼
┌──────────────┐   ┌──────────────────┐
│ Query Repair │   │ Build Answer     │
│ Agent        │   │ from rows        │
└──────┬───────┘   └──────────────────┘
       │ Repaired plan
       ▼
   Re-execute → Re-diagnose → Build Answer
         │
         ▼
┌─────────────────────┐
│  Explanation        │  Summarize pipeline decisions
│  Agent              │
└─────────────────────┘
```

## Agent Responsibilities

### 1. NL Understanding Agent
- Extracts keywords from the question by tokenizing and removing stopwords
- Classifies question type (exam, penalty, fee, duration, requirement, grade, etc.)
- Determines the aspect (exam_late, cheating, easycard_fee, graduation_credits, etc.)
- Maps vague questions to broader aspects for better query coverage

### 2. Security / Policy Agent
- Regex-based blocklist with 30+ unsafe patterns
- Detects injection attempts (Cypher injection, prompt injection)
- Blocks data exfiltration attempts (dump, export, credentials)
- Blocks mutation attempts (delete, merge, create, modify)
- Returns REJECT with reason for blocked queries

### 3. Query Planner Agent
- Maintains a mapping of 20+ aspects to pre-built Cypher queries
- Aspect-targeted queries use `CONTAINS` filters for precise matching
- Fallback uses fulltext indexes (`rule_idx`, `article_content_idx`) with keyword search
- Generates both Rule-node and Article-node queries for comprehensive coverage

### 4. Query Execution Agent
- Connects to Neo4j using environment variables (with defaults)
- Executes planned Cypher queries in read-only sessions
- Handles both parameterized fulltext queries and direct Cypher
- Returns structured rows with source type (rule/article) and relevance scores

### 5. Diagnosis Agent
- Classifies execution results into four states:
  - **SUCCESS**: Query returned matching rows
  - **QUERY_ERROR**: Execution threw an error
  - **SCHEMA_MISMATCH**: Error related to schema/index issues
  - **NO_DATA**: Query succeeded but returned no rows

### 6. Query Repair Agent
- Triggered on QUERY_ERROR, SCHEMA_MISMATCH, or NO_DATA
- Aspect-aware fallback: uses broader queries for known aspects (e.g., all exam rules)
- Keyword synonym expansion (test→exam, punishment→penalty, etc.)
- Fuzzy matching with Lucene `~` operator for broader fulltext coverage
- Maximum 1 repair round

### 7. Explanation Agent
- Produces a concise pipeline summary showing intent, security decision, diagnosis, and repair status

## Pipeline Design

**Hybrid flow (fixed front + dynamic back):**
1. **Fixed**: Understand → Security → Plan → Execute → Diagnose
2. **Dynamic**: If diagnosis is SUCCESS → build answer; if ERROR/NO_DATA → Repair → Re-execute → Re-diagnose → build answer

**Answer generation:**
- Prioritizes Article content (more readable, complete sentences)
- Supplements with Rule action/result data
- Adds concise prefix for yes/no questions ("No.") and quantity questions ("20 minutes.")
- Deduplicates overlapping content

## Key Design Decisions

1. **Aspect-targeted queries over pure fulltext**: Pre-built Cypher queries for known question aspects provide higher precision than generic fulltext search, especially for questions where keywords might not match index terms (e.g., "test" vs "exam").

2. **Dual-source answers (Rules + Articles)**: Articles contain complete, readable sentences while Rules have structured data. Combining both provides comprehensive and human-readable answers.

3. **Regex-based security over LLM-based**: Deterministic pattern matching ensures 100% rejection of known attack patterns without the latency and unpredictability of LLM-based filtering.

4. **NO_DATA triggers repair**: Treating empty results as repairable (not just errors) allows the system to recover from keyword mismatches through broader fallback queries.

## Challenges & Solutions

1. **Token matching in evaluation**: The evaluator checks exact substring or token overlap. Short expected answers like "No." or "20 minutes." required careful answer formatting with concise prefixes.

2. **Keyword-to-data mismatch**: Questions using "test" don't match rules containing "exam". Solved with synonym expansion in the repair agent and aspect-based planning that bypasses keyword search.

3. **Fulltext search limitations**: Lucene fulltext search with very vague keywords (e.g., "someone something okay") returns no results. Solved with aspect-aware repair fallbacks that use broader Cypher queries.

## Setup & Running

```bash
# Start Neo4j
docker start neo4j
# Or: docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest

# Install dependencies
pip install -r requirements.txt

# Build KG (if not already built)
python setup_data.py
python build_kg.py

# Run evaluation
python auto_test_a5.py
```

## Score

System Performance: **60.00 / 60**

| Component | Score |
|-----------|-------|
| Task Success Rate | 25.00 / 25 |
| Security & Validation | 15.00 / 15 |
| Error Detection Quality | 8.00 / 8 |
| Query Regeneration | 6.00 / 6 |
| Correct Resolution After Repair | 6.00 / 6 |
