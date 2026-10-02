"""
AI Resume Analyzer - Flask Application
Production-grade backend service for analyzing resumes against job descriptions,
extracting technical skills, computing match scores, and providing recommendations.
"""

import os
import re
import io
import json
import hashlib
import logging
from typing import Dict, List, Set, Tuple, Any

from flask import Flask, request, jsonify, render_template
import redis

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx
except ImportError:
    docx = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_resume_analyzer")

# Initialize Flask App
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB max upload

# ---------------------------------------------------------------------------
# Redis & In-Memory Caching Layer
# ---------------------------------------------------------------------------
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_TIMEOUT = float(os.environ.get("REDIS_TIMEOUT", 1.0))

class CacheManager:
    """Manages analysis caching with Redis and automatic in-memory fallback."""

    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT):
        self.host = host
        self.port = port
        self.in_memory_store: Dict[str, str] = {}
        self._redis_client = None

    def get_client(self):
        """Lazy connection to Redis with short timeout."""
        try:
            client = redis.Redis(
                host=self.host,
                port=self.port,
                socket_connect_timeout=REDIS_TIMEOUT,
                socket_timeout=REDIS_TIMEOUT,
                decode_responses=True
            )
            client.ping()
            return client
        except (redis.ConnectionError, redis.TimeoutError, Exception) as exc:
            logger.debug("Redis unreachable (%s:%s): %s. Using in-memory fallback.", self.host, self.port, exc)
            return None

    def is_connected(self) -> bool:
        """Returns True if Redis is reachable, otherwise False."""
        client = self.get_client()
        return client is not None

    def get(self, key: str) -> Any:
        client = self.get_client()
        if client:
            try:
                val = client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.warning("Error reading from Redis: %s", e)

        # In-memory fallback
        raw = self.in_memory_store.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        client = self.get_client()
        serialized = json.dumps(value)
        if client:
            try:
                client.setex(key, ttl_seconds, serialized)
                return
            except Exception as e:
                logger.warning("Error writing to Redis: %s", e)

        # In-memory fallback (limit size to prevent memory bloat)
        if len(self.in_memory_store) > 1000:
            self.in_memory_store.clear()
        self.in_memory_store[key] = serialized

cache_manager = CacheManager()

# ---------------------------------------------------------------------------
# Technical Skill Dictionary & Knowledge Base
# ---------------------------------------------------------------------------
TECHNICAL_TAXONOMY: Dict[str, Dict[str, Any]] = {
    # Cloud & DevOps
    "Docker": {"category": "DevOps & Containers", "pattern": r"\bdocker\b", "weight": 1.2},
    "Kubernetes": {"category": "DevOps & Containers", "pattern": r"\b(kubernetes|k8s)\b", "weight": 1.3},
    "Jenkins": {"category": "DevOps & Containers", "pattern": r"\bjenkins\b", "weight": 1.0},
    "Terraform": {"category": "Cloud & Infrastructure", "pattern": r"\bterraform\b", "weight": 1.2},
    "Ansible": {"category": "Cloud & Infrastructure", "pattern": r"\bansible\b", "weight": 1.0},
    "AWS": {"category": "Cloud & Infrastructure", "pattern": r"\b(aws|amazon\s+web\s+services)\b", "weight": 1.3},
    "Azure": {"category": "Cloud & Infrastructure", "pattern": r"\b(azure|microsoft\s+azure)\b", "weight": 1.2},
    "GCP": {"category": "Cloud & Infrastructure", "pattern": r"\b(gcp|google\s+cloud(\s+platform)?)\b", "weight": 1.2},
    "CI/CD": {"category": "DevOps & Containers", "pattern": r"\b(ci/cd|continuous\s+integration|continuous\s+delivery)\b", "weight": 1.1},
    "Linux": {"category": "Operating Systems", "pattern": r"\blinux\b", "weight": 1.0},
    "Git": {"category": "Version Control", "pattern": r"\b(git|github|gitlab|bitbucket)\b", "weight": 1.0},

    # Programming Languages
    "Python": {"category": "Languages", "pattern": r"\bpython\b", "weight": 1.3},
    "JavaScript": {"category": "Languages", "pattern": r"\b(javascript|js|es6)\b", "weight": 1.2},
    "TypeScript": {"category": "Languages", "pattern": r"\btypescript|ts\b", "weight": 1.2},
    "Java": {"category": "Languages", "pattern": r"\bjava\b(?!script)", "weight": 1.2},
    "Go": {"category": "Languages", "pattern": r"\b(golang|go\s+lang|go\s+programming)\b", "weight": 1.2},
    "C++": {"category": "Languages", "pattern": r"\bc\+\+\b", "weight": 1.1},
    "C#": {"category": "Languages", "pattern": r"\bc#|\bcsharp\b", "weight": 1.1},
    "Rust": {"category": "Languages", "pattern": r"\brust\b", "weight": 1.2},
    "Bash": {"category": "Languages", "pattern": r"\b(bash|shell\s+scripting)\b", "weight": 1.0},
    "SQL": {"category": "Languages", "pattern": r"\bsql\b", "weight": 1.2},

    # Web & Frameworks
    "React": {"category": "Frameworks & Libraries", "pattern": r"\b(react|react\.?js|reactjs)\b", "weight": 1.3},
    "Node.js": {"category": "Frameworks & Libraries", "pattern": r"\b(node\.?js|nodejs|node)\b", "weight": 1.2},
    "Flask": {"category": "Frameworks & Libraries", "pattern": r"\bflask\b", "weight": 1.1},
    "Django": {"category": "Frameworks & Libraries", "pattern": r"\bdjango\b", "weight": 1.2},
    "FastAPI": {"category": "Frameworks & Libraries", "pattern": r"\bfastapi\b", "weight": 1.1},
    "Next.js": {"category": "Frameworks & Libraries", "pattern": r"\b(next\.?js|nextjs)\b", "weight": 1.2},
    "Vue.js": {"category": "Frameworks & Libraries", "pattern": r"\b(vue\.?js|vuejs|vue)\b", "weight": 1.1},
    "Spring Boot": {"category": "Frameworks & Libraries", "pattern": r"\b(spring\s+boot|spring\s+framework)\b", "weight": 1.2},
    "Express": {"category": "Frameworks & Libraries", "pattern": r"\b(express\.?js|expressjs)\b", "weight": 1.0},
    "GraphQL": {"category": "APIs & Protocols", "pattern": r"\bgraphql\b", "weight": 1.1},
    "REST API": {"category": "APIs & Protocols", "pattern": r"\b(rest\s+api|restful\s+api|restful)\b", "weight": 1.1},

    # Databases & Storage
    "PostgreSQL": {"category": "Databases", "pattern": r"\b(postgresql|postgres)\b", "weight": 1.2},
    "MySQL": {"category": "Databases", "pattern": r"\bmysql\b", "weight": 1.1},
    "MongoDB": {"category": "Databases", "pattern": r"\bmongodb|mongo\b", "weight": 1.1},
    "Redis": {"category": "Databases", "pattern": r"\bredis\b", "weight": 1.1},
    "Elasticsearch": {"category": "Databases", "pattern": r"\belasticsearch\b", "weight": 1.1},

    # Machine Learning & Data
    "Machine Learning": {"category": "AI & Data Science", "pattern": r"\b(machine\s+learning|ml)\b", "weight": 1.2},
    "TensorFlow": {"category": "AI & Data Science", "pattern": r"\btensorflow\b", "weight": 1.2},
    "PyTorch": {"category": "AI & Data Science", "pattern": r"\bpytorch\b", "weight": 1.2},
    "Pandas": {"category": "AI & Data Science", "pattern": r"\bpandas\b", "weight": 1.0},
    "Kafka": {"category": "Streaming & Messaging", "pattern": r"\bkafka\b", "weight": 1.2},
    "Microservices": {"category": "Architecture", "pattern": r"\bmicroservices?\b", "weight": 1.1}
}

DEFAULT_BENCHMARK_SKILLS = [
    "Python", "Docker", "AWS", "SQL", "Git", "CI/CD", "Linux",
    "REST API", "PostgreSQL", "React", "Kubernetes", "Redis"
]

def extract_text_from_file(filename: str, content_bytes: bytes) -> str:
    """
    Extracts text content from various file formats:
    - PDF (.pdf) via pypdf
    - Word (.docx, .doc) via python-docx with binary fallback
    - Plain text, Markdown, RTF (.txt, .md, .rtf) via UTF-8/Latin-1 decoding
    """
    ext = os.path.splitext(filename.lower())[1]

    if ext == ".pdf":
        if pypdf is None:
            raise ValueError("pypdf is not installed on the system to parse PDF documents.")
        try:
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            pages_text = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    pages_text.append(extracted)
            result = "\n".join(pages_text).strip()
            if not result:
                raise ValueError("PDF file contains no extractable text (it may be a scanned image).")
            return result
        except Exception as exc:
            logger.error("Error extracting text from PDF '%s': %s", filename, exc)
            raise ValueError(f"Could not parse PDF file: {exc}")

    elif ext in [".docx", ".doc"]:
        # Attempt python-docx first (handles modern docx)
        if docx is not None:
            try:
                doc = docx.Document(io.BytesIO(content_bytes))
                lines = []
                for p in doc.paragraphs:
                    if p.text.strip():
                        lines.append(p.text)
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            if cell.text.strip():
                                lines.append(cell.text)
                extracted = "\n".join(lines).strip()
                if extracted:
                    return extracted
            except Exception as docx_exc:
                logger.debug("python-docx parsing failed for '%s': %s", filename, docx_exc)

        # Fallback for legacy .doc (OLE) or text files with .doc extension
        try:
            raw_text = content_bytes.decode("utf-8", errors="ignore")
            # Filter non-printable ASCII/control bytes
            clean_lines = [re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]", "", line) for line in raw_text.splitlines()]
            extracted = "\n".join(line.strip() for line in clean_lines if len(line.strip()) > 2)
            if extracted:
                return extracted
        except Exception as fb_exc:
            logger.debug("Fallback .doc parsing failed: %s", fb_exc)

        raise ValueError("Could not extract readable text from Word document. Please ensure it is a valid .docx or .doc file.")

    else:
        # Default text/markdown/rtf handling
        try:
            return content_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            return content_bytes.decode("latin-1", errors="ignore").strip()

def extract_skills_from_text(text: str) -> Set[str]:
    """Extracts known technical keywords from input text using case-insensitive regex."""
    if not text:
        return set()

    found_skills = set()
    for skill_name, skill_info in TECHNICAL_TAXONOMY.items():
        pattern = skill_info["pattern"]
        if re.search(pattern, text, re.IGNORECASE):
            found_skills.add(skill_name)
    return found_skills

def analyze_resume_matching(resume_text: str, job_description_text: str = "") -> Dict[str, Any]:
    """
    Computes a realistic candidate match score, matched/missing skills,
    category breakdown, and targeted AI recommendations.
    """
    resume_skills = extract_skills_from_text(resume_text)

    # If job description provided, extract its technical requirements
    # Otherwise compare against default industry benchmark skills
    jd_skills = extract_skills_from_text(job_description_text) if job_description_text.strip() else set(DEFAULT_BENCHMARK_SKILLS)

    if not jd_skills:
        jd_skills = set(DEFAULT_BENCHMARK_SKILLS)

    matched_skills = sorted(list(resume_skills.intersection(jd_skills)))
    missing_skills = sorted(list(jd_skills.difference(resume_skills)))
    additional_skills = sorted(list(resume_skills.difference(jd_skills)))

    # Weighted scoring algorithm
    matched_weight = sum(TECHNICAL_TAXONOMY.get(s, {}).get("weight", 1.0) for s in matched_skills)
    total_target_weight = sum(TECHNICAL_TAXONOMY.get(s, {}).get("weight", 1.0) for s in jd_skills)

    base_ratio = (matched_weight / total_target_weight) if total_target_weight > 0 else 0.0

    # Resume breadth bonus: extra relevant skills boost score by up to 10%
    breadth_bonus = min(len(additional_skills) * 0.02, 0.10)
    score_percentage = int(min(round((base_ratio + breadth_bonus) * 100), 100))

    # Category grouping
    categories: Dict[str, Dict[str, List[str]]] = {}
    for skill in matched_skills:
        cat = TECHNICAL_TAXONOMY.get(skill, {}).get("category", "General")
        categories.setdefault(cat, {"matched": [], "missing": []})
        categories[cat]["matched"].append(skill)

    for skill in missing_skills:
        cat = TECHNICAL_TAXONOMY.get(skill, {}).get("category", "General")
        categories.setdefault(cat, {"matched": [], "missing": []})
        categories[cat]["missing"].append(skill)

    # Dynamic AI Recommendations
    recommendations = []
    if score_percentage >= 85:
        recommendations.append("Outstanding match! Your profile demonstrates strong alignment with the target role.")
    elif score_percentage >= 65:
        recommendations.append("Solid alignment with the primary requirements, with a few notable technical skill gaps to bridge.")
    else:
        recommendations.append("Moderate match. Enhancing your resume with the high-priority missing technical keywords will significantly improve ATS ranking.")

    if missing_skills:
        top_missing = missing_skills[:4]
        recommendations.append(
            f"Add hands-on projects or production contributions featuring: {', '.join(top_missing)}."
        )

    # Section-specific actionable advice
    if "Docker" in missing_skills or "Kubernetes" in missing_skills:
        recommendations.append("Consider highlighting containerization and orchestration experience (e.g. Docker, Kubernetes clusters).")
    if "AWS" in missing_skills and "Azure" in missing_skills and "GCP" in missing_skills:
        recommendations.append("Cloud provider proficiency (AWS / Azure / GCP) is highly desired for modern infrastructure stacks.")
    if "CI/CD" in missing_skills or "Jenkins" in missing_skills:
        recommendations.append("Explicitly mention CI/CD pipelines, automated testing, or deployment automation workflows.")
    if not additional_skills and len(matched_skills) < 5:
        recommendations.append("Quantify your project outcomes using metrics (e.g., 'reduced latency by 35%', 'deployed 10+ microservices').")

    # Metrics summary
    return {
        "candidate_score": score_percentage,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "additional_skills": additional_skills,
        "skill_categories": categories,
        "matched_count": len(matched_skills),
        "missing_count": len(missing_skills),
        "total_skills_detected": len(resume_skills),
        "target_skills_count": len(jd_skills),
        "recommendations": recommendations,
        "job_description_provided": bool(job_description_text.strip())
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Renders the main single-page application."""
    return render_template("index.html")

@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check route returning JSON {"status": "UP"}.
    Also inspects Redis connectivity status.
    """
    is_redis_up = cache_manager.is_connected()
    return jsonify({
        "status": "UP",
        "redis_host": REDIS_HOST,
        "redis_connected": is_redis_up,
        "mode": "redis" if is_redis_up else "in-memory"
    }), 200

@app.route("/analyze", methods=["POST"])
def analyze_resume():
    """
    POST /analyze endpoint:
    Accepts raw resume text or file upload, plus optional target job description.
    Parses keywords, computes match score, and returns structured JSON analysis.
    """
    resume_text = ""
    job_description = ""

    # Handle JSON request body
    if request.is_json:
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({"error": "Invalid JSON payload provided"}), 400
        resume_text = payload.get("resume_text", "").strip()
        job_description = payload.get("job_description", "").strip()

    # Handle multipart/form-data or form-urlencoded
    else:
        # Check for uploaded file
        if "resume_file" in request.files:
            file = request.files["resume_file"]
            if file and file.filename != "":
                try:
                    content_bytes = file.read()
                    resume_text = extract_text_from_file(file.filename, content_bytes)
                except Exception as exc:
                    logger.error("Error parsing uploaded file '%s': %s", file.filename, exc)
                    return jsonify({"error": f"Failed to extract text from '{file.filename}': {str(exc)}"}), 400

        # Check form text fields
        if not resume_text and "resume_text" in request.form:
            resume_text = request.form.get("resume_text", "").strip()

        job_description = request.form.get("job_description", "").strip()

    # Validate that we have resume text to analyze
    if not resume_text:
        return jsonify({
            "error": "Resume content is required. Please provide 'resume_text' or upload a text file."
        }), 400

    # Check cache based on hash of inputs
    cache_key = "analysis:" + hashlib.sha256(
        (resume_text + "|||" + job_description).encode("utf-8")
    ).hexdigest()

    cached_result = cache_manager.get(cache_key)
    if cached_result:
        cached_result["cached"] = True
        return jsonify(cached_result), 200

    # Perform analysis
    result = analyze_resume_matching(resume_text, job_description)
    result["cached"] = False

    # Store in cache
    cache_manager.set(cache_key, result, ttl_seconds=1800)

    return jsonify(result), 200

# Error Handlers
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request", "message": str(error)}), 400

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api") or request.is_json:
        return jsonify({"error": "Resource not found"}), 404
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error("Internal server error: %s", error)
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    # Host 0.0.0.0 and port 5000 as strictly required
    app.run(host="0.0.0.0", port=5000, debug=True)
