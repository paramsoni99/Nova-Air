import os
import re
import subprocess
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_ai_context_integrity():
    """Verify AI_CONTEXT.md has all 17 sections, references Nova Air & nova_air_demo_v1, and has no legacy strings."""
    ai_context_path = os.path.join(ROOT_DIR, "AI_CONTEXT.md")
    assert os.path.exists(ai_context_path), "AI_CONTEXT.md must exist at root"

    with open(ai_context_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Verify 17 mandatory sections
    for i in range(1, 18):
        header_pattern = rf"##\s+{i}\.\s+"
        assert re.search(header_pattern, content), f"Missing section ## {i}. in AI_CONTEXT.md"

    # 2. Check canonical naming
    assert "Nova Air" in content, "AI_CONTEXT.md must reference 'Nova Air'"
    assert "nova_air_demo_v1" in content, "AI_CONTEXT.md must reference rule profile 'nova_air_demo_v1'"
    assert "demo_india_v1" not in content, "AI_CONTEXT.md must contain zero legacy 'demo_india_v1' references"


def test_required_local_documentation_and_skills():
    """Verify AGENTS.md, AI-HANDOFF-GUIDE.md, and all 6 skill files exist with YAML frontmatter."""
    agents_path = os.path.join(ROOT_DIR, "AGENTS.md")
    assert os.path.exists(agents_path), "AGENTS.md must exist"

    handoff_path = os.path.join(ROOT_DIR, "docs", "AI-HANDOFF-GUIDE.md")
    assert os.path.exists(handoff_path), "docs/AI-HANDOFF-GUIDE.md must exist"

    skill_names = [
        "project-context-maintenance",
        "ads-data-structures",
        "aviation-scheduling-constraints",
        "testing-and-verification",
        "operations-dashboard-ui",
        "regulatory-source-research",
    ]

    for name in skill_names:
        skill_path = os.path.join(ROOT_DIR, ".agents", "skills", name, "SKILL.md")
        assert os.path.exists(skill_path), f"Skill file {skill_path} must exist"
        with open(skill_path, "r", encoding="utf-8") as f:
            text = f.read()
        assert text.startswith("---"), f"Skill {name} must begin with YAML frontmatter '---'"
        assert f"name: {name}" in text, f"Skill {name} frontmatter missing name"
        assert "description:" in text, f"Skill {name} frontmatter missing description"


def test_gitignore_policy_enforcement():
    """Verify git check-ignore blocks local-only md/skills files while allowing build/code files."""
    gitignore_path = os.path.join(ROOT_DIR, ".gitignore")
    assert os.path.exists(gitignore_path), ".gitignore must exist"

    ignored_files = [
        "README.md",
        "AGENTS.md",
        "AI_CONTEXT.md",
        os.path.join("docs", "PROJECT-SPEC.md"),
        os.path.join(".agents", "skills", "project-context-maintenance", "SKILL.md"),
    ]

    for path in ignored_files:
        cmd = ["git", "check-ignore", path]
        result = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        assert result.returncode == 0, f"Expected {path} to be ignored by Git, but returncode was {result.returncode}"

    allowed_files = [
        os.path.join("backend", "requirements.txt"),
        os.path.join("frontend", "package.json"),
    ]

    for path in allowed_files:
        cmd = ["git", "check-ignore", path]
        result = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        assert result.returncode != 0, f"Expected {path} to NOT be ignored by Git, but was ignored"


def test_implemented_modules_exist_on_disk():
    """Verify every module marked IMPLEMENTED in AI_CONTEXT.md exists on disk."""
    ai_context_path = os.path.join(ROOT_DIR, "AI_CONTEXT.md")
    with open(ai_context_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Search for patterns like `path/to/file` <-- IMPLEMENTED
    for line in lines:
        if "NOT IMPLEMENTED" in line:
            continue
        if "IMPLEMENTED" in line and "`" in line:
            matches = re.findall(r"`([^`]+)`", line)
            for m in matches:
                # If it looks like a valid file path with a file extension
                if re.search(r"\.[a-zA-Z0-9_-]+$", m):
                    # Skip glob / braced patterns
                    if "{" in m or "*" in m:
                        continue
                    # Check direct path
                    direct_path = os.path.join(ROOT_DIR, m)
                    if os.path.exists(direct_path):
                        continue
                    # Check if file exists under any subdirectory
                    found = False
                    basename = os.path.basename(m)
                    for root, _, files in os.walk(ROOT_DIR):
                        if basename in files:
                            found = True
                            break
                    assert found, f"File '{m}' marked IMPLEMENTED in AI_CONTEXT.md was not found anywhere on disk"


def test_implemented_rest_routes_exist_in_fastapi():
    """Verify every REST route marked IMPLEMENTED in Section 10 of AI_CONTEXT.md exists in app.routes."""
    ai_context_path = os.path.join(ROOT_DIR, "AI_CONTEXT.md")
    with open(ai_context_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract Section 10 content
    sec10_match = re.search(r"## 10\. API and Real-Time Contracts(.*?)(?=## 11\.|\Z)", content, re.DOTALL)
    assert sec10_match, "Section 10 missing in AI_CONTEXT.md"
    sec10_text = sec10_match.group(1)

    from backend.app.main import app

    def collect_routes(router, prefix=""):
        res = set()
        for r in router.routes:
            if hasattr(r, "original_router") and hasattr(r, "include_context"):
                nested_pfx = prefix + getattr(r.include_context, "prefix", "")
                res.update(collect_routes(r.original_router, nested_pfx))
            else:
                methods = getattr(r, "methods", set())
                path = prefix + getattr(r, "path", "")
                for m in methods:
                    res.add((m.upper(), path))
                if not methods and path:
                    res.add(("WS", path))
        return res

    app_routes = collect_routes(app)

    # Match lines like: - `GET /api/v1/health`: ... (`IMPLEMENTED (VERIFIED)`)
    route_pattern = r"`(GET|POST|PATCH|PUT|DELETE|WS)\s+([^`]+)`.*?IMPLEMENTED"
    matches = re.findall(route_pattern, sec10_text)

    assert len(matches) > 0, "Expected at least one IMPLEMENTED route in Section 10 of AI_CONTEXT.md"

    for method, path in matches:
        if method == "WS":
            assert any(r[1] == path for r in app_routes), f"WebSocket route '{path}' from Section 10 not found in app.routes"
        else:
            assert (method, path) in app_routes, f"REST route '{method} {path}' marked IMPLEMENTED in Section 10 was not found in app.routes"

