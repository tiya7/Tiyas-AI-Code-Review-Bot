"""
Claude PR Reviewer Bot
======================
Uniquely reviews GitHub Pull Requests using Anthropic's Claude AI.

Features:
- Per-file severity-scored reviews (P0/P1/P2)
- Inline line-level comments on the PR
- Security/OWASP vulnerability detection
- Test coverage suggestions
- Auto-generated PR changelog summary
"""

import os
import sys
import json
import re
import anthropic
from github import Github, GithubException
from dataclasses import dataclass
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN      = os.environ["GITHUB_TOKEN"]
REPO_NAME         = os.environ["GITHUB_REPOSITORY"]          # e.g. "owner/repo"
PR_NUMBER         = int(os.environ["PR_NUMBER"])
MODEL             = os.getenv("CLAUDE_MODEL", "claude-opus-4-5")
MAX_DIFF_CHARS    = int(os.getenv("MAX_DIFF_CHARS", "12000"))  # per file

REVIEWABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rb", ".cs", ".cpp", ".c", ".h", ".rs", ".php",
    ".swift", ".kt", ".scala", ".sh", ".yaml", ".yml",
}

# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class FileReview:
    filename: str
    issues: list[dict]          # {severity, line, message, suggestion}
    security_flags: list[str]
    test_suggestions: list[str]
    summary: str
    score: int                  # 0-10 quality score


@dataclass
class PRReview:
    file_reviews: list[FileReview]
    overall_summary: str
    changelog: str
    top_issues: list[dict]
    overall_score: float

# ── Claude Prompts ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert senior AI engineer performing a thorough code review.
Your job is to review GitHub Pull Request diffs with extreme care.

For every review you produce valid JSON only — no markdown, no prose outside the JSON.

Severity levels:
  P0 = Critical (security hole, data loss, crash)
  P1 = High     (bug, performance regression, logic error)
  P2 = Medium   (code smell, readability, missing test)
  P3 = Low      (style, nitpick)

Security checks (always check for):
  - SQL / command injection
  - Hardcoded secrets / API keys
  - Insecure deserialization
  - Path traversal
  - Missing auth/authz checks
  - XSS / CSRF exposure
  - Unsafe use of eval / exec
"""

FILE_REVIEW_PROMPT = """Review the following file diff from a GitHub PR.

File: {filename}
Language: {language}

Diff:
```
{diff}
```

Return a JSON object with exactly this shape:
{{
  "issues": [
    {{
      "severity": "P0|P1|P2|P3",
      "line": <integer or null>,
      "message": "<concise problem description>",
      "suggestion": "<concrete fix or improvement>"
    }}
  ],
  "security_flags": ["<security concern if any>"],
  "test_suggestions": ["<specific test case to add>"],
  "summary": "<2-3 sentence file-level summary>",
  "score": <integer 0-10>
}}

Rules:
- Only flag real problems visible in the diff
- line numbers refer to NEW file line numbers from the diff header
- If no issues, return empty lists but still provide summary and score
- Be specific and actionable — no vague feedback
"""

OVERALL_SUMMARY_PROMPT = """You reviewed these files in a PR:

{file_summaries}

All issues found:
{all_issues}

Write a PR-level review as JSON:
{{
  "overall_summary": "<3-5 sentence executive summary of the PR quality>",
  "changelog": "<concise changelog entry suitable for CHANGELOG.md — present tense bullet points>",
  "top_issues": [
    {{
      "severity": "P0|P1|P2",
      "file": "<filename>",
      "message": "<issue>",
      "suggestion": "<fix>"
    }}
  ],
  "overall_score": <float 0.0-10.0>
}}

Top issues = at most 5 most important across all files. Focus on P0 and P1.
"""

# ── Core Logic ────────────────────────────────────────────────────────────────

class ClaudePRReviewer:
    def __init__(self):
        self.client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.github  = Github(GITHUB_TOKEN)
        self.repo    = self.github.get_repo(REPO_NAME)
        self.pr      = self.repo.get_pull(PR_NUMBER)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _detect_language(self, filename: str) -> str:
        ext_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React/JSX", ".tsx": "React/TSX", ".java": "Java",
            ".go": "Go", ".rb": "Ruby", ".cs": "C#", ".cpp": "C++",
            ".c": "C", ".rs": "Rust", ".php": "PHP", ".swift": "Swift",
            ".kt": "Kotlin", ".sh": "Shell", ".yaml": "YAML", ".yml": "YAML",
        }
        ext = os.path.splitext(filename)[-1].lower()
        return ext_map.get(ext, "Unknown")

    def _parse_json_response(self, text: str) -> dict:
        """Robustly extract JSON from Claude's response."""
        text = text.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.warning(f"JSON parse error: {e}. Attempting partial parse.")
            # Try to extract first JSON object
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise

    def _call_claude(self, prompt: str) -> str:
        message = self.client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    # ── File Review ──────────────────────────────────────────────────────────

    def _review_file(self, filename: str, patch: str) -> Optional[FileReview]:
        ext = os.path.splitext(filename)[-1].lower()
        if ext not in REVIEWABLE_EXTENSIONS:
            log.info(f"Skipping non-reviewable file: {filename}")
            return None

        language = self._detect_language(filename)
        diff_snippet = patch[:MAX_DIFF_CHARS] if patch else "(binary or empty)"

        prompt = FILE_REVIEW_PROMPT.format(
            filename=filename,
            language=language,
            diff=diff_snippet,
        )

        log.info(f"  Reviewing {filename} ({language})…")
        try:
            raw = self._call_claude(prompt)
            data = self._parse_json_response(raw)
        except Exception as e:
            log.error(f"Failed to review {filename}: {e}")
            return None

        return FileReview(
            filename=filename,
            issues=data.get("issues", []),
            security_flags=data.get("security_flags", []),
            test_suggestions=data.get("test_suggestions", []),
            summary=data.get("summary", ""),
            score=int(data.get("score", 5)),
        )

    # ── Overall Summary ──────────────────────────────────────────────────────

    def _build_overall_review(self, file_reviews: list[FileReview]) -> PRReview:
        file_summaries = "\n".join(
            f"- {r.filename} (score {r.score}/10): {r.summary}"
            for r in file_reviews
        )
        all_issues_list = []
        for r in file_reviews:
            for issue in r.issues:
                all_issues_list.append(
                    f"[{issue['severity']}] {r.filename}:{issue.get('line','?')} — {issue['message']}"
                )

        prompt = OVERALL_SUMMARY_PROMPT.format(
            file_summaries=file_summaries or "No files reviewed.",
            all_issues="\n".join(all_issues_list) or "None",
        )

        raw  = self._call_claude(prompt)
        data = self._parse_json_response(raw)

        return PRReview(
            file_reviews=file_reviews,
            overall_summary=data.get("overall_summary", ""),
            changelog=data.get("changelog", ""),
            top_issues=data.get("top_issues", []),
            overall_score=float(data.get("overall_score", 5.0)),
        )

    # ── GitHub Comment Posting ───────────────────────────────────────────────

    def _severity_emoji(self, sev: str) -> str:
        return {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "🔵"}.get(sev, "⚪")

    def _score_bar(self, score: float) -> str:
        filled = round(score)
        return "█" * filled + "░" * (10 - filled)

    def _post_main_comment(self, review: PRReview):
        """Post the main review summary as a PR comment."""
        score = review.overall_score
        bar   = self._score_bar(score)

        # Top issues table
        issue_rows = ""
        for i in review.top_issues:
            em  = self._severity_emoji(i["severity"])
            sev = i["severity"]
            f   = i.get("file", "")
            msg = i.get("message", "")
            sug = i.get("suggestion", "")
            issue_rows += f"| {em} `{sev}` | `{f}` | {msg} | {sug} |\n"

        # Per-file breakdown
        file_rows = ""
        for r in review.file_reviews:
            bar_f = self._score_bar(r.score)
            sec   = " 🔐" if r.security_flags else ""
            file_rows += f"| `{r.filename}` | `{r.score}/10` {bar_f}{sec} | {r.summary[:80]}… |\n"

        body = f"""## 🤖 Claude AI Code Review

> **Model:** `{MODEL}` &nbsp;|&nbsp; **PR:** #{PR_NUMBER} &nbsp;|&nbsp; **Overall Score:** `{score:.1f}/10`

```
Quality  [{bar}]  {score:.1f}/10
```

### 📋 Summary
{review.overall_summary}

---

### 🔥 Top Issues

| Severity | File | Issue | Suggestion |
|----------|------|-------|------------|
{issue_rows or "| ✅ | — | No critical issues found | — |\n"}

---

### 📁 Per-File Breakdown

| File | Score | Summary |
|------|-------|---------|
{file_rows or "| — | — | No files reviewed |\n"}

---

### 📝 Suggested Changelog Entry
```
{review.changelog}
```

---
<sub>🤖 Powered by [Claude AI](https://anthropic.com) · [claude-pr-reviewer](https://github.com)</sub>
"""
        self.pr.create_issue_comment(body)
        log.info("Posted main review comment.")

    def _post_inline_comments(self, file_reviews: list[FileReview]):
        """Post inline comments on specific lines in the PR diff."""
        commit = list(self.pr.get_commits())[-1]  # latest commit

        for fr in file_reviews:
            for issue in fr.issues:
                line = issue.get("line")
                if not line or not isinstance(line, int):
                    continue
                sev = issue.get("severity", "P2")
                em  = self._severity_emoji(sev)
                body = (
                    f"{em} **{sev}** — {issue['message']}\n\n"
                    f"> 💡 **Suggestion:** {issue.get('suggestion', 'N/A')}"
                )
                try:
                    self.pr.create_review_comment(
                        body=body,
                        commit=commit,
                        path=fr.filename,
                        line=line,
                    )
                    log.info(f"  Inline comment on {fr.filename}:{line}")
                except GithubException as e:
                    # Line might not be in diff — fall back silently
                    log.debug(f"  Could not comment on {fr.filename}:{line}: {e.data}")

    def _post_security_summary(self, file_reviews: list[FileReview]):
        """If security flags found, post a dedicated security comment."""
        flags = []
        for fr in file_reviews:
            for flag in fr.security_flags:
                flags.append(f"- `{fr.filename}`: {flag}")

        if not flags:
            return

        body = "## 🔐 Security Review Flags\n\n" + "\n".join(flags) + \
               "\n\n> Please address security concerns before merging."
        self.pr.create_issue_comment(body)
        log.info(f"Posted security summary ({len(flags)} flags).")

    # ── Entry Point ──────────────────────────────────────────────────────────

    def run(self):
        log.info(f"Starting Claude PR Review for {REPO_NAME}#{PR_NUMBER}")
        files = list(self.pr.get_files())
        log.info(f"Files changed: {len(files)}")

        file_reviews = []
        for f in files:
            review = self._review_file(f.filename, f.patch or "")
            if review:
                file_reviews.append(review)

        if not file_reviews:
            log.warning("No reviewable files found.")
            self.pr.create_issue_comment(
                "🤖 **Claude PR Reviewer**: No reviewable source files detected in this PR."
            )
            return

        log.info("Building overall review summary…")
        overall = self._build_overall_review(file_reviews)

        log.info("Posting comments to GitHub…")
        self._post_main_comment(overall)
        self._post_inline_comments(file_reviews)
        self._post_security_summary(file_reviews)

        log.info(f"✅ Review complete. Overall score: {overall.overall_score:.1f}/10")

        # Fail CI if P0 issues exist
        p0_count = sum(
            1 for fr in file_reviews
            for issue in fr.issues
            if issue.get("severity") == "P0"
        )
        if p0_count > 0:
            log.error(f"{p0_count} critical (P0) issue(s) found — marking CI as failed.")
            sys.exit(1)


if __name__ == "__main__":
    ClaudePRReviewer().run()
