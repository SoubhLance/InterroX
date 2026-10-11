"""Tests for app/services/resume_parser.py using synthetic data only."""

import json
from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest

from app.services.resume_parser import (
    extract_email,
    parse_sections,
    parse_with_llm,
)

SAMPLE = """Jane Doe
+1 (555) 010-2030 | jane.doe@example.com | linkedin.com/in/janedoe-example | github.com/janedoe-example

Summary
Software engineer with 3 years of experience building web APIs and data tools.

Education
State University
Bachelor of Science in Computer Science
August 2021 – May 2025

Experience
Backend Intern
June 2024 – August 2024
Acme Corp
Springfield, IL
• Built REST endpoints with FastAPI serving internal dashboards
used by 200 engineers
• Wrote unit tests with pytest covering core services

Projects
Chat App | FastAPI, Redis | GitHub
January 2025 – March 2025
• Implemented chat rooms with WebSocket support
for realtime messaging
• Added Redis caching to reduce database load

Skills
Languages: Python, C++, SQL
Tools: Git, Docker, Linux

Hobbies
Hiking and photography
"""


def test_extract_email_normal():
    assert extract_email("Contact me at jane.doe@example.com today") == "jane.doe@example.com"


def test_extract_email_uppercase():
    assert extract_email("Email: JANE.DOE@EXAMPLE.COM") == "jane.doe@example.com"


def test_extract_email_first_wins():
    text = "a first@example.com then second@example.com"
    assert extract_email(text) == "first@example.com"


def test_extract_email_none():
    assert extract_email("No email here, just text 123") is None
    assert extract_email("") is None


def test_full_sample_resume_sections():
    result = parse_sections(SAMPLE)
    assert set(result.keys()) == {
        "contact",
        "summary",
        "education",
        "skills",
        "projects",
        "experience",
        "other",
    }
    assert result["contact"]["name"] == "Jane Doe"
    assert result["contact"]["email"] == "jane.doe@example.com"
    assert "web APIs" in result["summary"]
    assert len(result["education"]) == 1
    edu = result["education"][0]
    assert set(edu.keys()) == {"institution", "degree", "year", "details"}
    assert edu["institution"] == "State University"
    assert "Bachelor" in edu["degree"]
    assert "2021" in edu["year"] and "2025" in edu["year"]
    assert edu["details"] == []
    assert len(result["experience"]) == 1
    exp = result["experience"][0]
    assert set(exp.keys()) == {"company", "role", "period", "bullets"}
    assert exp["role"] == "Backend Intern"
    assert exp["company"] == "Acme Corp"
    assert "2024" in exp["period"]
    assert len(exp["bullets"]) == 2
    assert len(result["projects"]) == 1
    proj = result["projects"][0]
    assert set(proj.keys()) == {"name", "description", "bullets", "tech"}
    assert proj["name"] == "Chat App"
    assert "WebSocket" in proj["description"]
    assert len(proj["bullets"]) == 2
    assert len(result["skills"]) > 0
    assert len(result["other"]) > 0


def test_wrapped_bullet_joined():
    result = parse_sections(SAMPLE)
    bullets = result["experience"][0]["bullets"]
    assert bullets[0] == (
        "Built REST endpoints with FastAPI serving internal dashboards "
        "used by 200 engineers"
    )
    proj_bullets = result["projects"][0]["description"]
    assert "with WebSocket support for realtime messaging" in proj_bullets


def test_project_header_tech():
    result = parse_sections(SAMPLE)
    proj = result["projects"][0]
    assert proj["name"] == "Chat App"
    assert proj["tech"] == ["FastAPI", "Redis"]
    assert all("github" not in t.lower() for t in proj["tech"])


def test_skills_categories_flat():
    result = parse_sections(SAMPLE)
    assert result["skills"] == ["Python", "C++", "SQL", "Git", "Docker", "Linux"]


def test_unknown_heading_to_other():
    result = parse_sections(SAMPLE)
    assert result["other"] == ["Hiking and photography"]


def test_missing_sections():
    result = parse_sections("Jane Doe\njane.doe@example.com\n")
    assert result["contact"]["name"] == "Jane Doe"
    assert result["contact"]["email"] == "jane.doe@example.com"
    assert result["summary"] == ""
    assert result["education"] == []
    assert result["skills"] == []
    assert result["projects"] == []
    assert result["experience"] == []
    assert result["other"] == []


def test_empty_string():
    result = parse_sections("")
    assert result["contact"] == {"name": "", "email": ""}
    assert result["summary"] == ""
    assert result["education"] == []
    assert result["skills"] == []
    assert result["projects"] == []
    assert result["experience"] == []
    assert result["other"] == []


def test_no_pii_in_output():
    result = parse_sections(SAMPLE)
    dump = json.dumps(result).lower()
    assert "555" not in dump
    assert "010-2030" not in dump
    assert "linkedin.com" not in dump
    assert "github.com" not in dump


def test_parse_with_llm_raises():
    with pytest.raises(NotImplementedError):
        parse_with_llm("some text")


def test_experience_order_company_period():
    text = (
        "Jane Doe\njane.doe@example.com\n\nExperience\n"
        "Software Engineer Intern\n"
        "December 2025 – January 2026\n"
        "Tech Solutions Ltd\n"
        "Bengaluru, India\n"
        "• Built API endpoints\n"
    )
    result = parse_sections(text)
    assert len(result["experience"]) == 1
    exp = result["experience"][0]
    assert set(exp.keys()) == {"company", "role", "period", "bullets"}
    assert exp["role"] == "Software Engineer Intern"
    assert exp["period"] == "December 2025 – January 2026"
    assert exp["company"] == "Tech Solutions Ltd"
    assert "Bengaluru" not in exp["company"]
    assert exp["bullets"] == ["Built API endpoints"]


def test_experience_location_after_date_skipped():
    text = (
        "Jane Doe\njane.doe@example.com\n\nExperience\n"
        "Data Intern\n"
        "May 2024 – July 2024\n"
        "Paris, France\n"
        "Globex Inc\n"
        "• Cleaned datasets\n"
    )
    exp = parse_sections(text)["experience"][0]
    assert exp["company"] == "Globex Inc"
    assert exp["period"] == "May 2024 – July 2024"
    assert "Paris" not in exp["company"]


def test_education_cgpa_details():
    text = (
        "Jane Doe\njane.doe@example.com\n\nEducation\n"
        "State University\n"
        "B.Tech in Computer Science\n"
        "2021 – 2025\n"
        "\n"
        "CGPA: 8.5\n"
        "Coursework: DSA, Operating Systems\n"
    )
    result = parse_sections(text)
    assert len(result["education"]) == 1
    edu = result["education"][0]
    assert edu["institution"] == "State University"
    assert "B.Tech" in edu["degree"]
    assert any("CGPA" in d for d in edu["details"])
    assert any("Coursework" in d for d in edu["details"])


def test_other_wrapped_paren_joined():
    text = (
        "Jane Doe\njane.doe@example.com\n\nAchievements\n"
        "• Winner of coding contest\n"
        "(among 500 participants)\n"
    )
    assert parse_sections(text)["other"] == [
        "Winner of coding contest (among 500 participants)"
    ]


def test_project_tech_drops_non_tech_segment():
    text = (
        "Jane Doe\njane.doe@example.com\n\nSkills\n"
        "Languages: Python, PyTorch\n\nProjects\n"
        "Vision Model | Python, PyTorch | Journal Published\n"
        "• Trained a classifier\n"
    )
    proj = parse_sections(text)["projects"][0]
    assert proj["name"] == "Vision Model"
    assert proj["tech"] == ["Python", "PyTorch"]
    assert all("Journal" not in t and "Publish" not in t for t in proj["tech"])


def test_project_single_word_tech_needs_skills():
    text = (
        "Jane Doe\njane.doe@example.com\n\nSkills\n"
        "Tools: Docker\n\nProjects\n"
        "Deploy Tool | Docker | GitHub\n"
        "• Shipped containers\n"
    )
    proj = parse_sections(text)["projects"][0]
    assert proj["tech"] == ["Docker"]


def test_project_bullets_and_description():
    text = (
        "Jane Doe\njane.doe@example.com\n\nProjects\n"
        "Chat App | FastAPI, Redis\n"
        "• First bullet here\n"
        "• Second bullet here\n"
    )
    proj = parse_sections(text)["projects"][0]
    assert proj["bullets"] == ["First bullet here", "Second bullet here"]
    assert proj["description"] == "First bullet here Second bullet here"


def test_experience_company_with_comma():
    text = (
        "Jane Doe\njane.doe@example.com\n\nExperience\n"
        "AI/ML Intern\n"
        "December 2025 – January 2026\n"
        "Eastern Coalfields Limited (ECL), A Subsidiary of Coal India\n"
        "Asansol, West Bengal\n"
        "• Built dashboard tools\n"
    )
    result = parse_sections(text)
    assert len(result["experience"]) == 1
    exp = result["experience"][0]
    assert exp["role"] == "AI/ML Intern"
    assert exp["period"] == "December 2025 – January 2026"
    assert exp["company"] == "Eastern Coalfields Limited (ECL), A Subsidiary of Coal India"
    assert "Asansol" not in exp["company"]
    assert exp["bullets"] == ["Built dashboard tools"]


def test_experience_no_location_line():
    text = (
        "Jane Doe\njane.doe@example.com\n\nExperience\n"
        "Research Intern\n"
        "June 2023 – August 2023\n"
        "North Lab\n"
        "• Ran experiments\n"
    )
    exp = parse_sections(text)["experience"][0]
    assert exp["role"] == "Research Intern"
    assert exp["period"] == "June 2023 – August 2023"
    assert exp["company"] == "North Lab"
    assert exp["bullets"] == ["Ran experiments"]


def test_bullet_unclosed_quote_wrap_joined():
    text = (
        "Jane Doe\njane.doe@example.com\n\nAchievements\n"
        "• Published in IJIRT: “OcuSight: Benchmark Performance vs. Clinical\n"
        "Multi-Disease Classification”\n"
    )
    assert parse_sections(text)["other"] == [
        "Published in IJIRT: “OcuSight: Benchmark Performance vs. Clinical "
        "Multi-Disease Classification”"
    ]


def test_bullet_unclosed_bracket_wrap_joined():
    text = (
        "Jane Doe\njane.doe@example.com\n\nAchievements\n"
        "• Built a parser (handling edge cases\n"
        "Found in production)\n"
    )
    assert parse_sections(text)["other"] == [
        "Built a parser (handling edge cases Found in production)"
    ]


def test_balanced_bullets_stay_separate():
    text = (
        "Jane Doe\njane.doe@example.com\n\nAchievements\n"
        "• First item with “quoted” text\n"
        "• Second item with (parenthetical) text\n"
    )
    assert parse_sections(text)["other"] == [
        "First item with “quoted” text",
        "Second item with (parenthetical) text",
    ]


def test_project_unclosed_quote_wrap_no_split():
    text = (
        "Jane Doe\njane.doe@example.com\n\nProjects\n"
        "Sight App | Python\n"
        "• Published results for “OcuSight: Benchmark\n"
        "Clinical Trials”\n"
        "• Second bullet here\n"
    )
    result = parse_sections(text)
    assert len(result["projects"]) == 1
    proj = result["projects"][0]
    assert proj["bullets"] == [
        "Published results for “OcuSight: Benchmark Clinical Trials”",
        "Second bullet here",
    ]
