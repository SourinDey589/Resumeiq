import os, json, re, requests, tempfile
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import fitz
from docx import Document
from io import BytesIO

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "resumeiq-secret-2024-xk9")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///resumeiq.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FREE_MODEL = "openrouter/free"
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}

# ─── MODELS ───────────────────────────────────────────────
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    api_key = db.Column(db.String(200), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    analyses = db.relationship('Analysis', backref='user', lazy=True)

class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200), default="Pasted Text")
    overall_score = db.Column(db.Integer, default=0)
    grammar_score = db.Column(db.Integer, default=0)
    vocabulary_score = db.Column(db.Integer, default=0)
    skills_score = db.Column(db.Integer, default=0)
    structure_score = db.Column(db.Integer, default=0)
    result_json = db.Column(db.Text)
    resume_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── HELPERS ──────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except Exception as e:
        raise ValueError(f"Could not read PDF: {str(e)}")

def extract_text_from_docx(file_bytes):
    try:
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        doc = Document(tmp_path)
        text = "\n".join([p.text for p in doc.paragraphs])
        os.unlink(tmp_path)
        return text.strip()
    except Exception as e:
        raise ValueError(f"Could not read DOCX: {str(e)}")

def extract_text(file):
    ext = file.filename.rsplit('.', 1)[1].lower()
    file_bytes = file.read()
    if ext == 'pdf':   return extract_text_from_pdf(file_bytes)
    elif ext == 'docx': return extract_text_from_docx(file_bytes)
    elif ext == 'txt':  return file_bytes.decode('utf-8', errors='ignore')
    raise ValueError("Unsupported file type")

def call_openrouter(prompt, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "ResumeIQ"
    }
    payload = {
        "model": FREE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.3
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise ValueError(f"OpenRouter API error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]

def parse_json_response(raw):
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()
    start, end = raw.find('{'), raw.rfind('}') + 1
    if start == -1 or end == 0:
        raise ValueError("No valid JSON in response")
    return json.loads(raw[start:end])

# ─── AUTH ROUTES ──────────────────────────────────────────
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pwd   = request.form.get('password', '')
        if not name or not email or not pwd:
            return jsonify({"error": "All fields are required"}), 400
        if len(pwd) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email already registered"}), 400
        user = User(name=name, email=email, password=generate_password_hash(pwd))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return jsonify({"success": True, "redirect": url_for('dashboard')})
    return render_template('auth.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pwd   = request.form.get('password', '')
        user  = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, pwd):
            return jsonify({"error": "Invalid email or password"}), 401
        login_user(user, remember=True)
        return jsonify({"success": True, "redirect": url_for('dashboard')})
    return render_template('auth.html', mode='login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# ─── DASHBOARD ────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    analyses = Analysis.query.filter_by(user_id=current_user.id)\
                             .order_by(Analysis.created_at.desc()).all()
    avg_score = round(sum(a.overall_score for a in analyses) / len(analyses)) if analyses else 0
    best_score = max((a.overall_score for a in analyses), default=0)
    return render_template('dashboard.html',
        analyses=analyses, avg_score=avg_score,
        best_score=best_score, total=len(analyses))

# ─── ANALYZE ──────────────────────────────────────────────
@app.route('/analyze', methods=['GET'])
@login_required
def analyze_page():
    return render_template('analyze.html')

@app.route('/api/analyze', methods=['POST'])
@login_required
def api_analyze():
    api_key = request.form.get('api_key', '').strip() or current_user.api_key
    if not api_key:
        return jsonify({"error": "Please provide your OpenRouter API key."}), 400

    filename = "Pasted Text"
    resume_text = ""

    if 'file' in request.files and request.files['file'].filename:
        f = request.files['file']
        if not allowed_file(f.filename):
            return jsonify({"error": "Only PDF, DOCX, TXT allowed."}), 400
        filename = f.filename
        try:
            resume_text = extract_text(f)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    elif request.form.get('text', '').strip():
        resume_text = request.form['text'].strip()
    else:
        return jsonify({"error": "Please upload a file or paste resume text."}), 400

    if len(resume_text) < 50:
        return jsonify({"error": "Resume text too short."}), 400

    # Save API key for user
    if api_key and api_key != current_user.api_key:
        current_user.api_key = api_key
        db.session.commit()

    prompt = f"""You are an expert resume reviewer and career coach. Analyze the resume and return ONLY a valid JSON object.

JSON structure:
{{
  "overall_score": <integer 0-100>,
  "grammar_score": <integer 0-100>,
  "vocabulary_score": <integer 0-100>,
  "skills_score": <integer 0-100>,
  "structure_score": <integer 0-100>,
  "summary": "<one sentence assessment>",
  "grammar_errors": [{{"original":"<wrong>","corrected":"<fix>","explanation":"<reason>"}}],
  "vocabulary_upgrades": [{{"original":"<weak>","improved":"<strong>"}}],
  "skills": ["<skill>"],
  "job_matches": [{{"role":"<title>","match_percentage":<int>,"reason":"<why>"}}],
  "suggestions": ["<tip>"],
  "ats_score": <integer 0-100>,
  "ats_issues": ["<ats issue>"],
  "sections_found": ["<section name>"],
  "sections_missing": ["<missing section>"]
}}

Rules: grammar_errors up to 5, vocabulary_upgrades up to 6, skills all detected, job_matches top 4, suggestions 5 tips, ats_score reflects ATS compatibility, ats_issues up to 4 ATS problems, sections_found and sections_missing list resume sections.

Resume:
---
{resume_text[:3500]}
---

Return ONLY the JSON."""

    try:
        raw = call_openrouter(prompt, api_key)
        result = parse_json_response(raw)

        # Save to DB
        a = Analysis(
            user_id=current_user.id,
            filename=filename,
            overall_score=result.get('overall_score', 0),
            grammar_score=result.get('grammar_score', 0),
            vocabulary_score=result.get('vocabulary_score', 0),
            skills_score=result.get('skills_score', 0),
            structure_score=result.get('structure_score', 0),
            result_json=json.dumps(result),
            resume_text=resume_text[:5000]
        )
        db.session.add(a)
        db.session.commit()

        return jsonify({"success": True, "data": result, "analysis_id": a.id})
    except (json.JSONDecodeError, ValueError) as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

# ─── JOB DESCRIPTION MATCHER ──────────────────────────────
@app.route('/job-matcher', methods=['GET'])
@login_required
def job_matcher_page():
    analyses = Analysis.query.filter_by(user_id=current_user.id)\
                             .order_by(Analysis.created_at.desc()).limit(10).all()
    return render_template('job_matcher.html', analyses=analyses)

@app.route('/api/job-match', methods=['POST'])
@login_required
def api_job_match():
    api_key = request.form.get('api_key', '').strip() or current_user.api_key
    if not api_key:
        return jsonify({"error": "API key required."}), 400

    resume_text = request.form.get('resume_text', '').strip()
    job_desc    = request.form.get('job_description', '').strip()
    analysis_id = request.form.get('analysis_id', '')

    if analysis_id:
        a = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
        if a: resume_text = a.resume_text or resume_text

    if not resume_text or not job_desc:
        return jsonify({"error": "Both resume and job description are required."}), 400

    prompt = f"""You are an expert ATS and recruitment specialist. Compare this resume against the job description and return ONLY valid JSON.

JSON structure:
{{
  "match_score": <integer 0-100>,
  "verdict": "<one sentence verdict>",
  "matched_keywords": ["<keyword found in both>"],
  "missing_keywords": ["<keyword in JD but not resume>"],
  "matched_skills": ["<skill that matches>"],
  "missing_skills": ["<skill required but missing>"],
  "experience_match": "<good/partial/poor>",
  "education_match": "<good/partial/poor/not mentioned>",
  "tone_match": "<professional/needs adjustment>",
  "strengths": ["<what resume does well for this JD>"],
  "gaps": ["<what resume is missing for this JD>"],
  "recommendations": ["<specific change to make resume fit better>"],
  "rewrite_summary": "<a rewritten resume summary tailored to this job>"
}}

Resume:
---
{resume_text[:2500]}
---

Job Description:
---
{job_desc[:2000]}
---

Return ONLY the JSON."""

    try:
        raw = call_openrouter(prompt, api_key)
        result = parse_json_response(raw)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── COVER LETTER GENERATOR ───────────────────────────────
@app.route('/cover-letter', methods=['GET'])
@login_required
def cover_letter_page():
    analyses = Analysis.query.filter_by(user_id=current_user.id)\
                             .order_by(Analysis.created_at.desc()).limit(10).all()
    return render_template('cover_letter.html', analyses=analyses)

@app.route('/api/cover-letter', methods=['POST'])
@login_required
def api_cover_letter():
    api_key      = request.form.get('api_key', '').strip() or current_user.api_key
    resume_text  = request.form.get('resume_text', '').strip()
    job_title    = request.form.get('job_title', '').strip()
    company_name = request.form.get('company_name', '').strip()
    job_desc     = request.form.get('job_description', '').strip()
    tone         = request.form.get('tone', 'professional')
    analysis_id  = request.form.get('analysis_id', '')

    if not api_key:
        return jsonify({"error": "API key required."}), 400
    if analysis_id:
        a = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
        if a: resume_text = a.resume_text or resume_text

    if not resume_text or not job_title:
        return jsonify({"error": "Resume text and job title are required."}), 400

    prompt = f"""You are a professional cover letter writer. Write a compelling cover letter and return ONLY valid JSON.

JSON structure:
{{
  "subject_line": "<email subject line>",
  "cover_letter": "<full cover letter with proper paragraphs, use \\n for line breaks>",
  "key_points_used": ["<what from resume was highlighted>"],
  "tone_used": "<tone description>",
  "word_count": <integer>
}}

Details:
- Candidate resume: {resume_text[:2000]}
- Job Title: {job_title}
- Company: {company_name or "the company"}
- Job Description: {job_desc[:1000] if job_desc else "Not provided"}
- Tone: {tone}
- Candidate name: {current_user.name}

Rules:
- 3-4 paragraphs, 250-350 words
- Opening: hook + position interest
- Body: 2 specific achievements from resume matching the role
- Closing: call to action
- Professional but {tone} tone
- Do NOT use placeholder brackets like [Your Name]

Return ONLY the JSON."""

    try:
        raw = call_openrouter(prompt, api_key)
        result = parse_json_response(raw)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── HISTORY / VIEW ───────────────────────────────────────
@app.route('/history/<int:analysis_id>')
@login_required
def view_analysis(analysis_id):
    a = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first_or_404()
    result = json.loads(a.result_json) if a.result_json else {}
    return render_template('result.html', analysis=a, result=result)

@app.route('/api/save-api-key', methods=['POST'])
@login_required
def save_api_key():
    key = request.json.get('api_key', '').strip()
    current_user.api_key = key
    db.session.commit()
    return jsonify({"success": True})

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/health')
def health():
    return jsonify({"status": "ok", "model": FREE_MODEL})

# ─── INIT ─────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    print("=" * 55)
    print("  ResumeIQ v2 — Flask + OpenRouter + SQLite")
    print("  http://localhost:5000")
    print("=" * 55)
    app.run(debug=True, host='0.0.0.0', port=5000)
