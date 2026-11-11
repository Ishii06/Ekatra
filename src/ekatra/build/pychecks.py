"""Checks for python-profile projects (API, CLI, library, data, database, game, automation).

Static checks parse every file with ``ast`` and verify that package imports resolve,
that the profile's required files exist and that tests are present. Runtime checks
execute the generated project in a separate Python process (project folder as the
working directory, secrets removed from the environment, hard timeouts): the
profile's entry commands first, then the project's own ``pytest`` suite.

Executing generated code is the point of this module: a project whose tests fail or
whose entry point crashes is not finished. It is controlled by the same
``smoke_test`` switch as the web smoke test.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ekatra.build.profiles import Profile
from ekatra.build.smoke import scrubbed_env
from ekatra.build.validate import Issue

ENTRY_TIMEOUT = 30
PYTEST_TIMEOUT = 120
_TAIL = 900

_API_SCRIPT = r'''
import json, traceback
out = {"errors": []}
try:
    from fastapi.testclient import TestClient
    import importlib
    module = importlib.import_module("__PKG__.main")
    with TestClient(module.app, raise_server_exceptions=False) as client:
        schema = client.get("/openapi.json")
        if schema.status_code != 200:
            out["errors"].append(f"GET /openapi.json returned HTTP {schema.status_code}")
        else:
            for path, ops in sorted(schema.json().get("paths", {}).items())[:15]:
                if "get" in ops and "{" not in path:
                    response = client.get(path)
                    if response.status_code >= 500:
                        out["errors"].append(f"GET {path} returned HTTP {response.status_code}")
except BaseException:
    out["errors"].append("the app failed to import or start:\n" + traceback.format_exc()[-900:])
print("EKATRA_API " + json.dumps(out))
'''


def _issue(severity: str, owner: str, file: str, description: str, missing_file: str = "") -> Issue:
    issue: Issue = {"severity": severity, "owner": owner, "file": file, "description": description}
    if missing_file:
        issue["missing_file"] = missing_file
    return issue


def _is_project_file(path: Path) -> bool:
    return "__pycache__" not in path.parts and ".pytest_cache" not in path.parts


def _owner(path: str, owners: dict[str, str], profile: Profile, default: str = "backend") -> str:
    role = owners.get(path) or ("qa" if path.startswith("tests/") else default)
    return role if role in profile.fixable_roles else default


# -- static ---------------------------------------------------------------------


def _module_exists(root: Path, dotted: str) -> bool:
    base = root / dotted.replace(".", "/")
    return base.with_suffix(".py").is_file() or base.is_dir()


def static_check(root: Path, pkg: str, profile: Profile, owners: dict[str, str] | None = None) -> list[Issue]:
    """Parse and cross-check the project's files without running them."""
    owners = owners or {}
    issues: list[Issue] = []
    for required in profile.required(pkg):
        if not (root / required).is_file():
            issues.append(_issue("high", _owner(required, owners, profile), required,
                                 f"required file {required} is missing", required))
    files = [p for d in (root / pkg, root / "tests") if d.is_dir() for p in sorted(d.rglob("*.py"))
             if _is_project_file(p)]
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            issues.append(_issue("high", _owner(rel, owners, profile), rel,
                                 f"syntax error line {exc.lineno}: {exc.msg}"))
            continue
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names if a.name == pkg or a.name.startswith(pkg + ".")]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module and (node.module == pkg or node.module.startswith(pkg + ".")):
                    targets = [node.module]
                elif node.level >= 1 and node.module and rel.startswith(pkg + "/"):
                    here = path.parent
                    for _ in range(node.level - 1):
                        here = here.parent
                    dotted = (here / node.module.replace(".", "/")).relative_to(root).as_posix().replace("/", ".")
                    targets = [dotted]
            for target in targets:
                if target != pkg and not _module_exists(root, target):
                    missing = target.replace(".", "/") + ".py"
                    issues.append(_issue("high", "backend", rel,
                                         f"imports module `{target}` which does not exist", missing))
    if not any(p.name.startswith("test_") for p in (root / "tests").rglob("*.py") if _is_project_file(p)):
        test_file = f"tests/test_{pkg}.py"
        issues.append(_issue("high", "qa", test_file, "the project has no tests (tests/test_*.py)", test_file))
    return issues


# -- runtime --------------------------------------------------------------------


def _run(argv: list[str], root: Path, *, stdin: str | None = None, timeout: int = ENTRY_TIMEOUT):
    """Run a command in the project; returns ``(returncode, output)`` or ``(None, message)`` on timeout."""
    env = scrubbed_env()
    try:
        done = subprocess.run(
            argv, cwd=root, env=env, capture_output=True, text=True, timeout=timeout,
            input=stdin if stdin is not None else None,
            stdin=None if stdin is not None else subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, f"did not finish within {timeout}s"
    except OSError as exc:
        return None, f"could not start: {exc}"
    return done.returncode, ((done.stdout or "") + (done.stderr or "")).strip()


def _blame(output: str, root: Path, pkg: str) -> tuple[str, str]:
    """``(package_file, test_file)`` of the deepest traceback frames inside the project.

    Understands both Python tracebacks (``File "x.py", line 3``) and pytest's short
    format (``app/core.py:3: in add``).
    """
    code = test = ""
    frames = re.findall(r'File "([^"]+)", line \d+', output)
    frames += re.findall(r"^\s*([\w./\\:-]+\.py):\d+: ", output, re.M)
    for frame in frames:
        try:
            path = Path(frame)
            rel = (path.resolve() if path.is_absolute() else (root / path).resolve()).relative_to(root.resolve())
        except (ValueError, OSError):
            continue
        rel_text = rel.as_posix()
        if rel_text.startswith(pkg + "/"):
            code = rel_text
        elif rel_text.startswith("tests/"):
            test = rel_text
    for match in re.findall(r"(tests/[\w./-]+\.py)", output.replace("\\", "/")):
        test = test or match
    return code, test


def _entry_commands(profile_key: str, pkg: str, tmp: str) -> list[tuple[str, list[str], str | None]]:
    py = sys.executable
    if profile_key == "cli":
        return [("python -m %s --help" % pkg, [py, "-m", pkg, "--help"], None)]
    if profile_key == "library":
        return [("import %s" % pkg, [py, "-c", f"import {pkg}"], None)]
    if profile_key in ("data", "database"):
        return [("python -m %s" % pkg, [py, "-m", pkg], None)]
    if profile_key == "game":
        return [("python -m %s (scripted: look, quit)" % pkg, [py, "-m", pkg], "look\nquit\n")]
    if profile_key == "automation":
        return [
            ("python -m %s --help" % pkg, [py, "-m", pkg, "--help"], None),
            ("python -m %s --target <sample folder> --dry-run" % pkg,
             [py, "-m", pkg, "--target", tmp, "--dry-run"], None),
        ]
    return []


def run_demo(root: Path, pkg: str, profile: Profile) -> list[dict]:
    """Run the profile's entry commands and report each result (used by checks and the API)."""
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ekatra-sample-") as tmp:
        for name in ("notes.txt", "photo.jpg", "report.pdf", "data.csv", "archive.zip"):
            (Path(tmp) / name).write_text("sample", encoding="utf-8")
        for label, argv, stdin in _entry_commands(profile.key, pkg, tmp):
            code, output = _run(argv, root, stdin=stdin)
            results.append({"command": label, "exit_code": code, "ok": code == 0, "output": output[-4000:]})
    return results


def _entry_issues(root: Path, pkg: str, profile: Profile, owners: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    if profile.key == "api":
        script = _API_SCRIPT.replace("__PKG__", pkg)
        code, output = _run([sys.executable, "-c", script], root)
        line = next((ln for ln in (output or "").splitlines() if ln.startswith("EKATRA_API ")), None)
        errors = json.loads(line[len("EKATRA_API "):])["errors"] if line else [
            f"the API check crashed: {(output or 'no output')[-500:]}"]
        main_file = f"{pkg}/main.py"
        for error in errors:
            blamed, _ = _blame(error, root, pkg)
            file = blamed or main_file
            issues.append(_issue("high", _owner(file, owners, profile), file, error[:700]))
        return issues
    for result in run_demo(root, pkg, profile):
        if result["ok"]:
            continue
        blamed, _ = _blame(result["output"], root, pkg)
        file = blamed or f"{pkg}/__main__.py"
        if not (root / file).is_file():
            file = next((r for r in profile.required(pkg) if r.startswith(pkg + "/")), f"{pkg}/__init__.py")
        status = "timed out" if result["exit_code"] is None else f"exited with code {result['exit_code']}"
        issues.append(_issue("high", _owner(file, owners, profile), file,
                             f"`{result['command']}` {status}: {result['output'][-_TAIL:]}"))
    if profile.key == "data" and not issues:
        out_dir = root / "output"
        if not out_dir.is_dir() or not any(p.is_file() for p in out_dir.rglob("*")):
            file = f"{pkg}/__main__.py"
            issues.append(_issue("high", _owner(file, owners, profile), file,
                                 "`python -m %s` ran but wrote nothing into output/" % pkg))
    return issues


def _imported_modules(root: Path, test_rel: str, pkg: str) -> list[str]:
    """Package files that a test file imports (``from pkg.x import y`` -> ``pkg/x.py``)."""
    try:
        tree = ast.parse((root / test_rel).read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []
    found: list[str] = []

    def add(dotted: str) -> None:
        base = dotted.replace(".", "/")
        for candidate in (f"{base}.py", f"{base}/__init__.py"):
            if (root / candidate).is_file() and candidate not in found and not candidate.endswith(
                    ("__init__.py", "__main__.py")):
                found.append(candidate)
                return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(pkg + "."):
                    add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.startswith(pkg + "."):
                add(node.module)
            elif node.module == pkg:  # from pkg import submodule
                for alias in node.names:
                    add(f"{pkg}.{alias.name}")
    return found


def _pytest_issues(root: Path, pkg: str, profile: Profile, owners: dict[str, str]) -> list[Issue]:
    argv = [sys.executable, "-m", "pytest", "-q", "-x", "--maxfail=3", "--tb=short", "-p", "no:cacheprovider", "tests"]
    code, output = _run(argv, root, timeout=PYTEST_TIMEOUT)
    if code == 0:
        return []
    tail = output[-_TAIL:]
    if code is None:
        return [_issue("high", "qa", "tests/", f"pytest {tail}")]
    if code == 5:
        test_file = f"tests/test_{pkg}.py"
        return [_issue("high", "qa", test_file, "pytest collected no tests; add tests/test_*.py", test_file)]
    code_file, test_file = _blame(output, root, pkg)
    issues: list[Issue] = []
    if "ModuleNotFoundError" in output or "ImportError" in output or "SyntaxError" in output:
        target = code_file or test_file or f"{pkg}/__init__.py"
        issues.append(_issue("high", _owner(target, owners, profile), target,
                             f"pytest could not run the tests:\n{tail}"))
        # "cannot import name X from pkg.mod": the module that should define X is at fault too
        missing = re.search(r"cannot import name '(\w+)' from '([\w.]+)'", output)
        if missing and missing.group(2).startswith(pkg):
            module = missing.group(2).replace(".", "/") + ".py"
            if module != target and (root / module).is_file():
                issues.append(_issue(
                    "high", _owner(module, owners, profile), module,
                    f"pytest could not import `{missing.group(1)}` from `{missing.group(2)}`. Define it there "
                    f"if the architecture or the change request requires it.\n{tail}"))
        return issues
    test_target = test_file or next((p for p, r in owners.items() if r == "qa" and p.startswith("tests/")),
                                    f"tests/test_{pkg}.py")
    if code_file:
        primaries = [code_file]
    else:
        # The failure happened inside the test itself (a failed assertion, or an expected
        # exception that never came). The code at fault is what the test imports - whoever
        # owns it, including the frontend developer's interface modules.
        primaries = _imported_modules(root, test_target, pkg)[:4]
        if not primaries:  # the test imports nothing from the package: any owned module could be at fault
            primaries = [p for p, r in owners.items() if r in ("backend", "frontend") and p.startswith(pkg + "/")
                         and not p.endswith(("__init__.py", "__main__.py"))][:4] or [f"{pkg}/__init__.py"]
    for primary in primaries:
        issues.append(_issue("high", _owner(primary, owners, profile), primary,
                             "A test fails. Change the code ONLY if it violates docs/architecture.md or has a bug; "
                             f"leave it alone if the test is wrong.\n{tail}"))
    if "qa" in profile.fixable_roles:
        issues.append(_issue("high", "qa", test_target,
                             "A test fails. Change the test ONLY if its expectation contradicts "
                             f"docs/architecture.md; leave it alone if the code is wrong.\n{tail}"))
    return issues


def runtime_check(root: Path, pkg: str, profile: Profile, owners: dict[str, str] | None = None) -> list[Issue]:
    """Run the entry commands and the project's tests; return what failed."""
    owners = owners or {}
    issues = _entry_issues(root, pkg, profile, owners)
    if (root / "tests").is_dir():
        issues += _pytest_issues(root, pkg, profile, owners)
    return issues


def check(root: Path, pkg: str, profile: Profile, owners: dict[str, str] | None = None,
          runtime: bool = True) -> list[Issue]:
    """Static checks, plus runtime checks when enabled and nothing is structurally broken."""
    issues = static_check(root, pkg, profile, owners)
    if runtime and not any(i["severity"] == "high" for i in issues):
        issues += runtime_check(root, pkg, profile, owners)
    return issues


def run_tests(root: Path) -> dict:
    """Run the project's pytest suite and report the result (used by the API)."""
    argv = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", "tests"]
    code, output = _run(argv, root, timeout=PYTEST_TIMEOUT)
    return {"command": "python -m pytest", "exit_code": code, "ok": code == 0, "output": output[-4000:]}


__all__ = ["check", "run_demo", "run_tests", "runtime_check", "static_check"]
