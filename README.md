# AI Resume Analyzer — Agile & DevOps Pipeline Integration

An end-to-end DevOps mini-project demonstrating a full Agile software development lifecycle, containerized multi-service deployment, automated CI/CD pipelines, and infrastructure monitoring for an **AI - Resume Analyzer** application.

---

## 🛠️ Tech Stack & Architecture

- **Application Backend:** Python (Flask), Pytest
- **Web Server & Reverse Proxy:** Nginx
- **Databases & Cache:** MySQL, Redis, phpMyAdmin
- **Containerization:** Docker, Docker Compose
- **CI/CD Pipelines:** Jenkins (Declarative & Scripted SCM Pipelines), GitHub Actions
- **Agile & Workflows:** Jira Cloud + GitHub for Jira Integration
- **Monitoring:** Nagios Core, NSClient++ (Windows NRPE agent)

---

## 📋 DevOps Pipeline Flow

```text
Jira (Plan/Sprint) 
  └─► Git Branching (Code & Feature Work)
        └─► GitHub Actions & Webhooks (Trigger)
              └─► Jenkins Pipeline (Build ➔ Test ➔ Deploy)
                    └─► Docker Compose (Multi-Container Deployment)
                          └─► Nagios Core (Infrastructure Monitoring)

## Build 9 Test Line
## Testing Automated Trigger
