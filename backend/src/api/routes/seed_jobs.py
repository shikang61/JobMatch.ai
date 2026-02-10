"""
Seed sample jobs for development. Not mounted in production or require admin auth.
"""
from datetime import date, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import CurrentUserId
from src.api.middleware.rate_limit import check_api_rate_limit
from src.database.connection import get_db
from src.models.job import Job
from src.config import get_settings

router = APIRouter()

SAMPLE_JOBS = [
    {
        "company_name": "TechCorp Inc",
        "job_title": "Senior Software Engineer",
        "job_description": "We are looking for a Senior Software Engineer to build scalable backend services. You will work with Python, PostgreSQL, and AWS. Experience with FastAPI and async Python is a plus. You will lead architecture decisions for our microservices platform.",
        "required_skills": ["Python", "PostgreSQL", "REST APIs", "AWS"],
        "preferred_skills": ["FastAPI", "Docker", "Redis", "Kubernetes"],
        "experience_level": "senior",
        "experience_years_range": "5-7",
        "location": "Remote",
        "source": "seed",
    },
    {
        "company_name": "StartupXYZ",
        "job_title": "Full Stack Developer",
        "job_description": "Full stack role: React and Node.js. You will own features end-to-end. We use TypeScript, React Query, and PostgreSQL. Fast-paced startup environment with direct product impact.",
        "required_skills": ["JavaScript", "React", "Node.js", "TypeScript"],
        "preferred_skills": ["PostgreSQL", "AWS", "Tailwind CSS"],
        "experience_level": "mid",
        "experience_years_range": "3-5",
        "location": "New York, NY",
        "source": "seed",
    },
    {
        "company_name": "DataDriven Co",
        "job_title": "Backend Engineer",
        "job_description": "Backend services in Python and Go. Kafka, event-driven systems, and data pipelines. SQL and NoSQL experience required. You will build and maintain real-time data processing systems.",
        "required_skills": ["Python", "Go", "SQL", "Kafka"],
        "preferred_skills": ["AWS", "Docker", "Redis", "Terraform"],
        "experience_level": "mid",
        "experience_years_range": "3-5",
        "location": "San Francisco, CA",
        "source": "seed",
    },
    {
        "company_name": "CloudScale Systems",
        "job_title": "DevOps Engineer",
        "job_description": "Manage and improve our cloud infrastructure on AWS and GCP. Automate deployments with Terraform and CI/CD pipelines. Monitor and optimize system performance. On-call rotation required.",
        "required_skills": ["AWS", "Docker", "Kubernetes", "Terraform", "CI/CD"],
        "preferred_skills": ["Python", "Go", "Prometheus", "Grafana"],
        "experience_level": "mid",
        "experience_years_range": "3-5",
        "location": "Remote",
        "source": "seed",
    },
    {
        "company_name": "FinTech Global",
        "job_title": "Python Developer",
        "job_description": "Build high-performance trading systems and data analysis pipelines. Work with Python, pandas, NumPy. Strong understanding of financial markets is a plus. Emphasis on code quality and testing.",
        "required_skills": ["Python", "SQL", "pandas", "REST APIs"],
        "preferred_skills": ["NumPy", "FastAPI", "Redis", "PostgreSQL"],
        "experience_level": "mid",
        "experience_years_range": "2-4",
        "location": "London, UK",
        "source": "seed",
    },
    {
        "company_name": "HealthTech Solutions",
        "job_title": "Frontend Engineer",
        "job_description": "Build intuitive healthcare dashboards with React and TypeScript. Accessibility (WCAG 2.1) compliance is critical. Work closely with designers and product managers to deliver patient-facing features.",
        "required_skills": ["React", "TypeScript", "CSS", "HTML"],
        "preferred_skills": ["Next.js", "Tailwind CSS", "Jest", "Accessibility"],
        "experience_level": "mid",
        "experience_years_range": "2-4",
        "location": "Boston, MA",
        "source": "seed",
    },
    {
        "company_name": "AI Innovations Lab",
        "job_title": "Machine Learning Engineer",
        "job_description": "Design, train, and deploy ML models for NLP and computer vision. Work with PyTorch, transformers, and cloud ML platforms. Collaborate with research scientists to productionize models.",
        "required_skills": ["Python", "PyTorch", "Machine Learning", "SQL"],
        "preferred_skills": ["Docker", "AWS", "Kubernetes", "MLflow"],
        "experience_level": "senior",
        "experience_years_range": "4-7",
        "location": "Remote",
        "source": "seed",
    },
    {
        "company_name": "E-Commerce Plus",
        "job_title": "Junior Software Developer",
        "job_description": "Great opportunity for early-career developers. Work on our e-commerce platform using Python and React. Mentorship and growth opportunities. Pair programming and code reviews are part of our culture.",
        "required_skills": ["Python", "JavaScript", "HTML", "CSS"],
        "preferred_skills": ["React", "SQL", "Git"],
        "experience_level": "entry",
        "experience_years_range": "0-2",
        "location": "Austin, TX",
        "source": "seed",
    },
]


@router.post("/seed-jobs")
async def seed_jobs(
    user_id: CurrentUserId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Insert sample jobs if none exist. For development only."""
    check_api_rate_limit(request, user_id)
    if get_settings().environment != "development":
        raise HTTPException(404, "Not available")
    result = await db.execute(select(Job).limit(1))
    if result.scalar_one_or_none():
        return {"message": "Jobs already exist", "count": 0}
    for i, j in enumerate(SAMPLE_JOBS):
        job = Job(
            company_name=j["company_name"],
            job_title=j["job_title"],
            job_description=j["job_description"],
            required_skills=j["required_skills"],
            preferred_skills=j["preferred_skills"],
            experience_level=j["experience_level"],
            experience_years_range=j["experience_years_range"],
            location=j["location"],
            job_url=f"https://example.com/job/{uuid4().hex[:12]}",
            source=j["source"],
            posted_date=date.today() - timedelta(days=i * 5),
            is_active=True,
        )
        db.add(job)
    await db.commit()
    return {"message": "Seeded sample jobs", "count": len(SAMPLE_JOBS)}
