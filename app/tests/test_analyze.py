import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app

def test_home_page_loads():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200