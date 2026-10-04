"""
Pytest Unit Test Suite for AI Resume Analyzer
Validates the core Flask endpoints: GET /, GET /health, and POST /analyze.
"""

import io
import os
import sys
import pytest

# Ensure parent directory (app) and project root are in sys.path
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import app

@pytest.fixture
def client():
    """Create a configured Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_index_route(client):
    """
    Test 1: Verify GET / returns HTTP status 200 and loads the SPA.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert b"AI Resume Analyzer" in response.data

def test_health_route(client):
    """
    Test 2: Verify GET /health returns HTTP status 200 and JSON payload containing {"status": "UP"}.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, dict)
    assert data.get("status") == "UP"

def test_analyze_route_success(client):
    """
    Test 3: Verify POST /analyze returns correct 200 status code and comprehensive JSON layout.
    """
    payload = {
        "resume_text": """
        Experienced Senior Software Engineer with expertise in Python, Docker, AWS,
        PostgreSQL, and React. Built scalable microservices and CI/CD pipelines.
        Proficient in SQL and Linux administration.
        """,
        "job_description": """
        Looking for a DevOps / Full-Stack Engineer skilled in:
        Python, Docker, Kubernetes, Jenkins, Terraform, AWS, and React.
        """
    }

    response = client.post(
        "/analyze",
        json=payload,
        content_type="application/json"
    )

    assert response.status_code == 200
    data = response.get_json()

    # Verify structured JSON keys
    assert "candidate_score" in data
    assert "matched_skills" in data
    assert "missing_skills" in data
    assert "recommendations" in data
    assert "skill_categories" in data

    # Verify types and content
    assert isinstance(data["candidate_score"], int)
    assert 0 <= data["candidate_score"] <= 100
    assert "Python" in data["matched_skills"]
    assert "Docker" in data["matched_skills"]
    assert "AWS" in data["matched_skills"]
    assert "React" in data["matched_skills"]

    # Verify missing skills identified from the target job description
    assert "Kubernetes" in data["missing_skills"] or "Terraform" in data["missing_skills"] or "Jenkins" in data["missing_skills"]
    assert len(data["recommendations"]) > 0

def test_analyze_empty_payload_returns_400(client):
    """
    Test 4: Verify error handling on missing/empty resume text returns HTTP 400.
    """
    response = client.post(
        "/analyze",
        json={"resume_text": ""},
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

def test_analyze_file_upload(client):
    """
    Test 5: Verify POST /analyze accepts multipart/form-data file uploads.
    """
    resume_content = b"Tech Lead with hands-on experience in Python, AWS, Docker, Git, and SQL."
    data = {
        "resume_file": (io.BytesIO(resume_content), "resume.txt"),
        "job_description": "We need Python and AWS developers."
    }

    response = client.post(
        "/analyze",
        data=data,
        content_type="multipart/form-data"
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["candidate_score"] > 0
    assert "Python" in result["matched_skills"]
    assert "AWS" in result["matched_skills"]

def test_analyze_docx_file_upload(client):
    """
    Test 6: Verify POST /analyze accepts and extracts text from Word (.docx) documents.
    """
    import docx
    doc = docx.Document()
    doc.add_paragraph("Principal Cloud Engineer with Kubernetes, Terraform, Docker, and AWS experience.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    data = {
        "resume_file": (buf, "resume.docx"),
        "job_description": "Must have hands-on Kubernetes, Terraform, and Docker."
    }

    response = client.post(
        "/analyze",
        data=data,
        content_type="multipart/form-data"
    )
    assert response.status_code == 200
    result = response.get_json()
    assert "Kubernetes" in result["matched_skills"]
    assert "Terraform" in result["matched_skills"]
    assert "Docker" in result["matched_skills"]

def test_analyze_pdf_file_upload(client):
    """
    Test 7: Verify POST /analyze accepts and extracts text from PDF documents.
    """
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Full Stack Developer proficient in Python, React, FastAPI, and PostgreSQL.")
    c.save()
    buf.seek(0)

    data = {
        "resume_file": (buf, "candidate_cv.pdf"),
        "job_description": "We are seeking Python, React, and PostgreSQL talent."
    }

    response = client.post(
        "/analyze",
        data=data,
        content_type="multipart/form-data"
    )
    assert response.status_code == 200
    result = response.get_json()
    assert "Python" in result["matched_skills"]
    assert "React" in result["matched_skills"]
    assert "PostgreSQL" in result["matched_skills"]
