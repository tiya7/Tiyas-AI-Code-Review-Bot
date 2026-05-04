# 🤖 Tiyas AI Chat Reviewer Bot

> Automatically review GitHub Pull Requests using **Anthropic Claude AI** — with severity scoring, inline comments, security scanning, and auto-generated changelogs.

---

## ✨ What Makes This Unique

| Feature | Typical GPT Bot | This Bot |
|---------|----------------|----------|
| AI Engine | GPT-4 | **Claude (Anthropic)** |
| Issue Severity | Basic | **P0/P1/P2/P3 priority labels** |
| Comment Type | Single summary | **Inline line-level + summary** |
| Security | Optional | **Built-in OWASP checks always on** |
| Test Coverage | No | **Per-function test suggestions** |
| Changelog | No | **Auto-generated CHANGELOG entry** |
| CI Gate | No | **Fails CI if P0 issues exist** |
| Score | No | **0-10 quality score with bar viz** |

---

## 📋 Prerequisites

### 1. Python 3.11+
```bash
# macOS
brew install python@3.11

# Ubuntu/Debian
sudo apt update && sudo apt install python3.11 python3.11-venv python3-pip -y

# Windows — download from https://python.org/downloads
```

### 2. pip packages
```bash
pip install anthropic PyGithub python-dotenv
```
Or: `pip install -r requirements.txt`

### 3. Anthropic API Key
- Sign up at https://console.anthropic.com
- Create an API key under **API Keys**
- Copy it — you'll need it below

### 4. GitHub Personal Access Token (PAT)
- Go to GitHub → **Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens**
- Click **Generate new token**
- Required permissions:
  - `Pull requests` → Read & Write
  - `Issues` → Read & Write
  - `Contents` → Read (to read file diffs)
- Copy the token

### 5. Git (obviously 😄)
```bash
git --version   # should print git version 2.x
```

---

## 🚀 Step-by-Step Setup (Run in 1 Go)

### Step 1 — Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/claude-pr-reviewer.git
cd claude-pr-reviewer
```

### Step 2 — Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows PowerShell
```

### Step 3 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 4 — Set up environment variables
```bash
cp .env.example .env
```
Now open `.env` in any editor and fill in:
```
ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
GITHUB_TOKEN=ghp_YOUR_TOKEN_HERE
GITHUB_REPOSITORY=your-github-username/your-repo-name
PR_NUMBER=1
```

### Step 5 — Test locally against a real PR
```bash
python scripts/test_local.py --repo owner/repo --pr 42
```

Add `--dry-run` to print the review without posting to GitHub:
```bash
python scripts/test_local.py --repo owner/repo --pr 42 --dry-run
```

### Step 6 — Deploy to GitHub Actions (automated on every PR)

**a)** Copy the workflow to your target repo:
```bash
mkdir -p YOUR_REPO/.github/workflows
cp .github/workflows/claude-review.yml YOUR_REPO/.github/workflows/
```

**b)** Add secrets to your GitHub repo:
- Go to your repo → **Settings → Secrets and variables → Actions**
- Click **New repository secret**
- Add:
  - `ANTHROPIC_API_KEY` → your Anthropic key
  - (GitHub automatically provides `GITHUB_TOKEN` — no action needed)

**c)** Push the workflow file and open a PR — the bot runs automatically! 🎉

---

## 📂 Project Structure

```
claude-pr-reviewer/
├── .github/
│   └── workflows/
│       └── claude-review.yml   ← GitHub Actions workflow
├── src/
│   └── reviewer.py             ← Main bot logic
├── scripts/
│   └── test_local.py           ← Local testing script
├── requirements.txt
├── .env.example                ← Copy to .env and fill in keys
├── .gitignore
└── README.md
```

---

## 🔧 Configuration Options

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key |
| `GITHUB_TOKEN` | — | **Required.** GitHub PAT or Actions token |
| `GITHUB_REPOSITORY` | — | **Required.** `owner/repo` format |
| `PR_NUMBER` | — | **Required.** PR number to review |
| `CLAUDE_MODEL` | `claude-opus-4-5` | Claude model to use |
| `MAX_DIFF_CHARS` | `12000` | Max diff characters per file |

---

## 💬 What the Bot Posts

### 1. Main Summary Comment
- Overall quality score (0-10) with visual bar
- Executive summary
- Top issues table (severity + file + fix)
- Per-file breakdown table
- Auto-generated changelog entry

### 2. Inline PR Comments
- Posted directly on the line in the diff
- Severity-labeled (🔴 P0 / 🟠 P1 / 🟡 P2 / 🔵 P3)
- Includes actionable suggestion

### 3. Security Alert Comment (if issues found)
- Dedicated comment listing all OWASP-style security flags
- Blocks merge visually

---

## ⚠️ CI Gate

If the bot finds **any P0 (critical) issue**, the GitHub Actions job exits with code 1, marking the CI check as **failed**. You can enforce this as a required check in branch protection rules.

---

## 🛡️ Privacy & Safety

- Diffs are sent to Anthropic's API — do NOT use on repos with sensitive/proprietary code unless you have an Anthropic data agreement
- Never commit your `.env` file — it's in `.gitignore` by default
- Use fine-grained GitHub tokens with minimum required permissions

---

## 📄 License

MIT — do whatever you want, just don't blame us if Claude roasts your code 😄
Built with lovw by Tiya❤️
