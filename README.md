
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![OpenRouter](https://img.shields.io/badge/AI-OpenRouter-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

# ResumeIQ — AI Resume Analyzer
### Flask + OpenRouter + SQLite + Use  Auth

---

## Features
- User Register / Login / Logout
- Resume Analyzer (Grammar, Vocab, Skills, ATS, Job Match)
- Job Description Matcher (keyword gap analysis)
- Cover Letter Generator (tailored, downloadable)
- Score History Dashboard
- API Key saved per user

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run
python app.py

# 3. Open browser
http://localhost:5000
```

---

## Project Structure

```
resumeiq_v2/
├── app.py                  ← Main Flask app
├── requirements.txt
├── resumeiq.db             ← Auto-created SQLite DB
└── templates/
    ├── base.html           ← Sidebar layout
    ├── landing.html        ← Homepage
    ├── auth.html           ← Login / Register
    ├── dashboard.html      ← User dashboard
    ├── analyze.html        ← Resume analyzer
    ├── job_matcher.html    ← JD matcher
    ├── cover_letter.html   ← Cover letter generator
    ├── result.html         ← View saved result
    └── settings.html       ← User settings
```

---

## Get Free OpenRouter API Key
1. Go to https://openrouter.ai/keys
2. Sign up (no credit card)
3. Create key → paste in Settings page
4. Key is saved for all future use

## Free Model Used
`openrouter/free` — automatically picks best available free model
