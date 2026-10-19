# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-80eadd5a
"""IP and policy file-scan audit. Prints IPSCAN_OK.

Scans the repository's source and documentation files for:
  (i)   forbidden model identifiers, consensus/voting terminology, prompt
        templates, and secrets-shaped strings;
  (ii)  any description of the answering service beyond the single allowed
        disclosure sentence (see README.md for the canonical allowed wording);
  (iii) per audit fix #844, any use of the standard-library mocking
        framework or its helpers (imports, decorators, patchers) in test
        or source files.

Forbidden terms are assembled at runtime from fragments so this audit file
never contains the patterns it scans for (which would make the scan match
itself). No mock frameworks. No third-party test framework is imported:
the scan needs a git checkout and exits with a plain message (not IPSCAN_OK)
when run from a zip download without a .git directory.
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Verify we're in the correct repository by checking for a known root file
EXPECTED_ROOT_FILE = "README.md"

SCAN_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".html", ".css",
                 ".md", ".txt", ".json", ".yaml", ".yml")

SELF = os.path.normcase(os.path.abspath(__file__))

# Files where SQL or generator vocabulary is expected and allowed.
SELECT_ALLOWED = {
    "northstar/gen_data.py",
}

def _frag(*parts):
    return "".join(parts)

# Model/vendor identifiers that must never appear anywhere in the repo.
# Using word boundaries to prevent false positives
MODEL_TERMS = [
    _frag(r"\bme", r"ta\.l", r"la", r"ma\b"),
    _frag(r"\bmis", r"tral\.\b"),
    _frag(r"\bqw", r"en\b"),
    _frag(r"\bama", r"zon\.no", r"va\b"),
    _frag(r"\bgem", r"ini\b"),
    _frag(r"\bgp", r"t-\d\b"),
    _frag(r"\bcla", r"ude\b"),
    _frag(r"\bbed", r"rock\b"),  # runtime vendor naming forbidden
    _frag(r"\bopen", r"router\b"),
]

# Method/answering-logic terminology forbidden by the owner IP ruling.
METHOD_TERMS = [
    _frag(r"\bconsensus\b"),
    _frag(r"\bplurality\b"),
    _frag(r"\bmodels?\s+agreed\b"),
    _frag(r"\bmodels?\s+disagreed\b"),
    _frag(r"\broster\b"),
    _frag(r"\bpanel\s+of\b"),
    _frag(r"\bgrounding\b"),
    _frag(r"\bgrounded\s+search\b"),
    _frag(r"\bvoting\b"),
    _frag(r"\bself-consistency\b"),
]

# Secrets-shaped and hygiene patterns (regexes) across source files.
ALL_FILE_REGEXES = [
    _frag(r"\bexample\.com\b"),
    _frag(r"\blorem ipsum\b"),
    _frag(r"\bor-[a-z]\b"),
    _frag(r"\bcdn\.\b"),
]

# Source-code specific regexes (Python, JavaScript, HTML only)
SOURCE_REGEXES = [
    _frag(r"\bunittest\.mock\b"),
    _frag(r"\bfrom\s+unittest\s+import\s+mock\b"),
    _frag(r"\bMagicMock\b"),
    _frag(r"\bmock\.patch\b"),
    _frag(r"\bNonCallableMock\b"),
    _frag(r"\bPropertyMock\b"),
    _frag(r"\bapi_key\s*=\s*[\"']"),
    _frag(r"\bsk-[A-Za-z0-9]{20}\b"),
]

# Combined regexes for all files (secrets only)
SECRETS_REGEXES = [
    _frag(r"\bapi_key\s*=\s*[\"']"),
    _frag(r"\bsk-[A-Za-z0-9]{20}\b"),
]

# Regex pattern for the exact allowed disclosure sentence
ALLOWED_DISCLOSURE_PATTERN = re.compile(
    r"powered\s+by\s+our\s+proprietary\s+discovery\s+model\s+and\s+proprietary\s+evolution\s+module",
    re.IGNORECASE
)

# Pattern to match the full allowed disclosure sentence with optional punctuation/whitespace
FULL_DISCLOSURE_PATTERN = re.compile(
    r"powered\s+by\s+our\s+proprietary\s+discovery\s+model\s+and\s+proprietary\s+evolution\s+module\.",
    re.IGNORECASE
)

def _iter_files():
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", ".venv",
                                    "venv", ".aws-sam", "node_modules")]
        for name in filenames:
            if name.endswith(SCAN_SUFFIXES) or name in (
                    "LICENSE", "Dockerfile", ".gitignore", ".dockerignore"):
                yield os.path.join(dirpath, name)

def _rel(path):
    rel_path = os.path.relpath(path, REPO_ROOT)
    # Normalize path separators to forward slashes for consistent output
    return rel_path.replace(os.sep, "/")

def _check_repo_root():
    """Run the repository-root checks. Done inside main() so importing this
    module (e.g. during test collection) has no side effects."""
    if not os.path.exists(os.path.join(REPO_ROOT, EXPECTED_ROOT_FILE)):
        raise SystemExit(f"ERROR: Not running from project root. Expected to find '{EXPECTED_ROOT_FILE}' in '{REPO_ROOT}'")

    # Additional validation: check for .git directory to ensure we're in a proper repo root.
    # Plain exit (no third-party test framework): the scan is skipped, not passed,
    # so IPSCAN_OK is deliberately not printed.
    if not os.path.exists(os.path.join(REPO_ROOT, ".git")):
        print("IPSCAN_SKIPPED: no .git directory (zip download); "
              "IP scan needs a git checkout", file=sys.stderr)
        raise SystemExit(0)

def main():
    _check_repo_root()

    failures = []

    for path in _iter_files():
        # Use normcase for case-insensitive comparison on all platforms
        if os.path.normcase(os.path.abspath(path)) == SELF:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError as e:
            failures.append("%s: UnicodeDecodeError - %s" % (_rel(path), str(e)))
            continue
        except OSError as e:
            failures.append("%s: OSError - %s" % (_rel(path), str(e)))
            continue
            
        lowered = text.lower()
        rel = _rel(path)

        for term_pattern in MODEL_TERMS:
            if re.search(term_pattern, lowered, re.IGNORECASE):
                failures.append("%s: forbidden model/vendor term" % rel)
        for term_pattern in METHOD_TERMS:
            if re.search(term_pattern, lowered, re.IGNORECASE):
                failures.append("%s: forbidden method term" % rel)

        # Apply all-file regexes to all file types
        for pattern in ALL_FILE_REGEXES:
            if re.search(pattern, text, re.IGNORECASE):
                failures.append("%s: forbidden pattern" % rel)
                
        # Apply secrets regexes to all file types
        for pattern in SECRETS_REGEXES:
            if re.search(pattern, text, re.IGNORECASE):
                failures.append("%s: potential secret pattern" % rel)

        # Apply source-specific regexes to source files and Dockerfile
        if path.endswith((".py", ".js", ".mjs", ".cjs", ".html")) or os.path.basename(path) == "Dockerfile":
            for pattern in SOURCE_REGEXES:
                if re.search(pattern, text, re.IGNORECASE):
                    failures.append("%s: forbidden source pattern" % rel)

        # Check for SQL usage with case-insensitive regex in source files
        if path.endswith((".py", ".js", ".mjs", ".cjs", ".html")):
            # Normalize path for comparison
            normalized_path = _rel(path)
            if (re.search(r"\bselect\b", text, re.IGNORECASE) and 
                normalized_path not in SELECT_ALLOWED):
                failures.append("%s: SQL keyword outside the data generator" % rel)

        # Any description of the answering service must be the allowed
        # disclosure sentence and nothing more.
        if "proprietary discovery model" in lowered:
            # Check if the exact allowed disclosure is present
            if not ALLOWED_DISCLOSURE_PATTERN.search(text):
                failures.append("%s: partial/disallowed disclosure wording" % rel)
            # Additional check for full sentence integrity
            elif not FULL_DISCLOSURE_PATTERN.search(text.strip()):
                failures.append("%s: disclosure sentence not properly formed" % rel)

    for failure in failures:
        print("  FAIL - " + failure)
    if failures:
        raise SystemExit("IPSCAN FAILED (%d finding(s))" % len(failures))
    print("  ok - no forbidden model, method, or secret patterns found")
    print("  ok - no mocking framework usage in any source file "
          "(audit fix #844)")
    print("  ok - answering service is described only by the allowed "
          "disclosure sentence")
    print("IPSCAN_OK")

if __name__ == "__main__":
    main()
