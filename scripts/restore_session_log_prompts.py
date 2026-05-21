#!/usr/bin/env python3
"""Restore verbatim task prompts into session logs (global integrity audit)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/opt/assistant-flow")
SESSIONS = ROOT / "docs/cursor_sessions"
TASKS = ROOT / "cursor_tasks_local"

ALIASES: dict[str, str] = {
    "2026-05-15_evaluation_ragas_operational_verification": "evaluation_ragas_operational_verification_prompt_ru.md",
    "2026-05-15_rag_memory_leakage_diagnostic": "rag_memory_leakage_diagnostic_prompt_ru.md",
    "2026-05-15_ragas_admin_api_dependency_fix": "ragas_admin_api_dependency_fix_prompt_ru.md",
    "2026-05-15_ragas_negative_absence_inconsistency_diagnostic": "ragas_negative_absence_inconsistency_diagnostic_prompt_ru.md",
    "2026-05-15_ragas_skipped_diagnostic": "ragas_skipped_diagnostic_prompt_ru.md",
    "2026-05-16_evaluation_analysis_run_panel_cleanup": "evaluation_rag_analysis_run_panel_cleanup_prompt_ru.md",
    "2026-05-16_evaluation_recent_rag_turns_ui_russification": "evaluation_rag_recent_turns_ui_russification_prompt_ru.md",
    "2026-05-19_security-rbac-architecture-audit": "2026-05-19_security_rbac_architecture_audit_ru.md",
    "2026-05-19_security_console_canonical_alignment_fix": "cursor_prompt_rag_ui_rollback_and_security_console_alignment.md",
    "2026-05-20_p9-6-rbac-retrieval-restrictions": "p_9_6_rbac_retrieval_restrictions_prompt.md",
}

SUMMARY_SECTIONS = re.compile(
    r"^## (Исходный промпт \(кратко\)|Prompt \(кратко\)|Task Envelope|Полный prompt \(задача\)|Полный prompt \(источник задачи\))\s*$",
    re.MULTILINE,
)

FINDINGS_START = re.compile(
    r"^## (?!Полный prompt)(?!0\.)(?!1\. Контекст)(?!Языковая)(README |docs |UI |Incident|Изменён|Changed|Navigation|Root|SQL|Verification|Build|Operator|Append|Матрица|Сценар|Smoke|List item|Top panels|Retrieval security|Scenario model|1\. Current|2\. Cognitive|Evaluation|RAGAS|Diagnostic|Workspace|Post-fix|docs actualization|README surgical|OCR|Security audit|Architecture|Implementation|Findings|Краткий|ДО →|Security console|Audit|Git diff|Build/Deploy|Operator commands|git status)",
    re.MULTILINE,
)


def find_task_file(session_path: Path) -> Path | None:
    stem = session_path.stem
    if stem in ALIASES:
        p = TASKS / ALIASES[stem]
        return p if p.exists() else None
    text = session_path.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"cursor_tasks_local/([^\s`\)]+\.md)", text):
        p = TASKS / m.group(1)
        if p.exists():
            return p
    p = TASKS / f"{stem}.md"
    return p if p.exists() else None


def extract_header(text: str) -> str:
    """Title block through first --- or before first summary/findings."""
    m = re.search(r"\n---\n", text)
    if m and m.start() < 800:
        return text[: m.start()].rstrip()
    # no early ---: take until summary or findings
    for pat in [SUMMARY_SECTIONS, FINDINGS_START]:
        m2 = pat.search(text)
        if m2 and m2.start() > 20:
            return text[: m2.start()].rstrip()
    lines = text.splitlines()
    header_lines = []
    for line in lines[:12]:
        if line.startswith("## ") and "Задача" not in line and "Task" not in line:
            break
        header_lines.append(line)
    return "\n".join(header_lines).rstrip()


def extract_findings(text: str) -> str:
    """Body after prompt/summary sections."""
    # strip existing ## Полный prompt ... block
    text = re.sub(
        r"\n## Полный prompt[^\n]*\n.*?(?=\n---\n|\n## [^#]|\Z)",
        "",
        text,
        count=1,
        flags=re.DOTALL,
    )
    # strip summary sections
    while True:
        m = SUMMARY_SECTIONS.search(text)
        if not m:
            break
        start = m.start()
        rest = text[m.end() :]
        nxt = FINDINGS_START.search(rest)
        if nxt:
            text = text[:start] + rest[nxt.start() :]
        else:
            # drop until next ## at same level that's not numbered task section
            nxt2 = re.search(r"\n## (?!Полный)(?!0\.)(?!1\. )", rest)
            if nxt2:
                text = text[:start] + rest[nxt2.start() :]
            else:
                text = text[:start]
                break
    # remove header
    header = extract_header(text)
    body = text[len(header) :].lstrip("\n")
    body = re.sub(r"^---\n+", "", body)
    return body.strip()


def restore_session(session_path: Path, task_path: Path) -> str:
    text = session_path.read_text(encoding="utf-8", errors="replace")
    task_text = task_path.read_text(encoding="utf-8").strip()
    if task_text in text:
        return text

    header = extract_header(text)
    findings = extract_findings(text)
    task_ref = f"cursor_tasks_local/{task_path.name}"

    parts = [header, "", "---", "", "## Полный prompt", "", f"Источник: `{task_ref}`", "", task_text, "", "---", ""]
    if findings:
        parts.append(findings)
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    changed = []
    for sp in sorted(SESSIONS.glob("*.md")):
        if "global-session-log" in sp.name:
            continue
        tp = find_task_file(sp)
        if not tp:
            continue
        tt = tp.read_text(encoding="utf-8").strip()
        old = sp.read_text(encoding="utf-8")
        if tt in old:
            continue
        new = restore_session(sp, tp)
        if new != old:
            sp.write_text(new, encoding="utf-8")
            changed.append(sp.name)
    print(f"Restored: {len(changed)}")
    for name in changed:
        print(f"  {name}")


if __name__ == "__main__":
    main()
