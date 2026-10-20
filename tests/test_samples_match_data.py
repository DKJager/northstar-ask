import os
import subprocess
import sys


def test_samples_match_dataset():
    """Pin samples/responses.json to the fictional dataset.

    Runs `samples/build_samples.py --check` and asserts exit code 0.
    Prevents a future edit that breaks agreement between the generated
    samples and the dataset from passing the test suite.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(repo_root, "samples", "build_samples.py")

    result = subprocess.run(
        [sys.executable, script, "--check"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    stdout = result.stdout
    stderr = result.stderr
    assertion_message = (
        f"samples/build_samples.py --check failed with exit code {result.returncode}.\n"
        f"STDOUT:\n{stdout}\n"
        f"STDERR:\n{stderr}"
    )

    assert result.returncode == 0, assertion_message
