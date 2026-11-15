"""Static safety check and isolated subprocess runner for untrusted rebuilt model code and its tests."""

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_IMPORTS = {"pandas", "numpy", "math", "statsmodels", "scipy", "sklearn", "typing", "dataclasses"}
TEST_EXTRA_IMPORTS = {"pytest", "model"}
FORBIDDEN_CALLS = {"eval", "exec", "open", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr", "breakpoint", "input"}
FORBIDDEN_ATTRIBUTE = re.compile(
    r"^(read_\w+|to_(csv|pickle|parquet|excel|json|hdf|sql|feather|stata|html|xml|clipboard|latex|markdown)|"
    r"load|loads|save|savez|savez_compressed|savetxt|loadtxt|genfromtxt|fromfile|tofile|memmap|ctypeslib|system|popen)$"
)
DEFAULT_TIMEOUT_SECONDS = 120
MEMORY_LIMIT_BYTES = 4 * 1024**3
FILE_SIZE_LIMIT_BYTES = 500 * 1024**2

SCORING_RUNNER = '''
import json, sys
sys.path.insert(0, ".")
import pandas as pd
import model

dev = pd.read_csv(sys.argv[1])
oot = pd.read_csv(sys.argv[2])
coefficients = None
refit = None
if hasattr(model, "fit"):
    refit = model.fit(dev)["coefficients"]
    refit = {str(k): float(v) for k, v in refit.items()}
    if not model.DEPLOYED_COEFFICIENTS:
        coefficients = refit
for name, frame in (("dev", dev), ("oot", oot)):
    scored = model.score(frame, coefficients=coefficients)
    scored[["ID", "pd", "score", "decision"]].to_csv(f"scored_{name}.csv", index=False, float_format="%.17g")
with open("refit_coefficients.json", "w") as handle:
    json.dump(refit, handle)
'''


class UnsafeCodeError(ValueError):
    """Raised when code fails the static safety check."""


@dataclass
class SandboxResult:
    """Outcome of one isolated run."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    outputs: dict[str, Path] = field(default_factory=dict)


def check_code(source: str, extra_allowed: set[str] = frozenset()) -> list[str]:
    """Return the list of safety violations in the source (empty when the code is acceptable)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"syntax error: {error}"]
    allowed = ALLOWED_IMPORTS | set(extra_allowed)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [(node.module or "").split(".")[0]] if node.level == 0 else ["relative import"]
        else:
            roots = []
        violations += [f"line {node.lineno}: import of '{root}' is not allowed" for root in roots if root not in allowed]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            violations.append(f"line {node.lineno}: call to '{node.func.id}' is not allowed")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("__") or FORBIDDEN_ATTRIBUTE.match(node.attr)):
            violations.append(f"line {node.lineno}: access to attribute '{node.attr}' is not allowed")
        if isinstance(node, ast.Name) and node.id.startswith("__") and node.id not in {"__name__"}:
            violations.append(f"line {node.lineno}: use of name '{node.id}' is not allowed")
    return violations


def limit_resources() -> None:
    """Child process limits: memory, size of written files, no core dumps (POSIX only, best effort)."""
    import resource

    for limit, value in ((resource.RLIMIT_AS, MEMORY_LIMIT_BYTES), (resource.RLIMIT_FSIZE, FILE_SIZE_LIMIT_BYTES),
                         (resource.RLIMIT_CORE, 0)):
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass  # some platforms (macOS for RLIMIT_AS) refuse a limit; the others still apply


def run_isolated(files: dict[str, str], args: list[str], timeout: int = DEFAULT_TIMEOUT_SECONDS,
                 collect: tuple[str, ...] = (), keep_dir: Path | None = None) -> SandboxResult:
    """Write the files to a fresh temporary folder and run 'python -I <args>' there with a clean environment."""
    with tempfile.TemporaryDirectory(prefix="redev_sandbox_") as tmp:
        workdir = Path(tmp)
        for name, content in files.items():
            (workdir / name).write_text(content, encoding="utf-8")
        environment = {"PATH": "/usr/bin:/bin", "HOME": tmp, "PYTHONHASHSEED": "0", "MPLBACKEND": "Agg"}
        try:
            completed = subprocess.run(
                [sys.executable, "-I", *args], cwd=workdir, env=environment,
                capture_output=True, text=True, timeout=timeout,
                preexec_fn=limit_resources if sys.platform != "win32" else None,
            )
            result = SandboxResult(completed.returncode, completed.stdout, completed.stderr, False)
        except subprocess.TimeoutExpired as expired:
            stdout = expired.stdout.decode() if isinstance(expired.stdout, bytes) else (expired.stdout or "")
            return SandboxResult(-1, stdout, f"Stopped after the {timeout} second time limit.", True)
        if keep_dir is not None:
            keep_dir.mkdir(parents=True, exist_ok=True)
            for name in collect:
                if (workdir / name).exists():
                    result.outputs[name] = Path(shutil.copy(workdir / name, keep_dir / name))
        return result


def run_tests(model_source: str, test_source: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[SandboxResult, int, int]:
    """Check both files, run pytest on them in isolation and return the result with passed and failed counts."""
    violations = check_code(model_source) + check_code(test_source, TEST_EXTRA_IMPORTS)
    if violations:
        raise UnsafeCodeError("; ".join(violations))
    files = {"model.py": model_source, "test_model.py": test_source}
    result = run_isolated(files, ["-m", "pytest", "-q", "-p", "no:cacheprovider", "test_model.py"], timeout)
    passed, failed = count_pytest_outcomes(result.stdout)
    if result.timed_out or (passed + failed == 0 and result.returncode != 0):
        failed = max(failed, 1)
    return result, passed, failed


def count_pytest_outcomes(output: str) -> tuple[int, int]:
    """Parse 'N passed' and 'M failed' / 'K error' from the final pytest summary line."""
    summary = next((line for line in reversed(output.splitlines()) if re.search(r" in [\d.]+s", line)), "")

    def count(word: str) -> int:
        """Number in front of one outcome word in the summary line."""
        return sum(int(n) for n in re.findall(rf"(\d+) {word}\b", summary))
    return count("passed"), count("failed") + count("errors?")


def run_scoring(model_source: str, dev_path: Path, oot_path: Path, out_dir: Path,
                timeout: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[SandboxResult, dict | None]:
    """Check the model, then score dev and oot (and refit when fit exists) in isolation; outputs go to out_dir."""
    violations = check_code(model_source)
    if violations:
        raise UnsafeCodeError("; ".join(violations))
    result = run_isolated(
        {"model.py": model_source, "run_scoring.py": SCORING_RUNNER},
        ["run_scoring.py", str(Path(dev_path).resolve()), str(Path(oot_path).resolve())],
        timeout,
        collect=("scored_dev.csv", "scored_oot.csv", "refit_coefficients.json"),
        keep_dir=out_dir,
    )
    refit_path = result.outputs.pop("refit_coefficients.json", None)
    refit = json.loads(refit_path.read_text()) if refit_path else None
    if refit_path:
        refit_path.unlink()
    return result, refit
