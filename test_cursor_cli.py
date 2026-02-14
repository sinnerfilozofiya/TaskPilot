#!/usr/bin/env python3
"""
Minimal script to verify we can talk to Cursor CLI.
Run from TaskPilot root:
  python test_cursor_cli.py          # quick test: ask CLI to reply "OK"
  python test_cursor_cli.py hello    # create a simple hello.py (in ./cursor_test_out/)
Uses .env in this directory for CURSOR_API_KEY.
"""
import os
import subprocess
import sys
from pathlib import Path

# Project root = directory containing this script
ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"

def load_env():
    if not ENV_FILE.exists():
        print("No .env found at", ENV_FILE)
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            elif v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
            os.environ[k] = v

def run_cli(cmd: list, cwd: str, env: dict, timeout_sec: int) -> tuple[int, str, str]:
    """Run CLI command; return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    return result.returncode, result.stdout or "", result.stderr or ""

def main():
    load_env()
    key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    print("CURSOR_API_KEY set:", bool(key))
    if not key:
        print("Set CURSOR_API_KEY in .env and run again.")
        sys.exit(1)

    use_hello = len(sys.argv) > 1 and sys.argv[1].lower() == "hello"
    if use_hello:
        out_dir = ROOT / "cursor_test_out"
        out_dir.mkdir(exist_ok=True)
        cwd = str(out_dir)
        prompt = (
            "Create a single file hello.py in this directory that contains exactly: "
            "print('Hello, world'). Write only that file, nothing else. Use -f/--force if needed."
        )
        print("Mode: hello world (output dir:", cwd, ")")
    else:
        cwd = str(ROOT)
        prompt = 'Reply with only the word OK and nothing else. No explanation, no code.'
        print("Mode: quick reply test")

    env = dict(os.environ)
    env["CURSOR_API_KEY"] = key
    timeout_sec = 120 if use_hello else 90

    # Try "agent" first (per Cursor docs), then "cursor agent". Use -f for file writes in hello mode.
    base_agent = ["agent", "-p"]
    base_cursor = ["cursor", "agent", "-p"]
    if use_hello:
        base_agent.extend(["-f", prompt])
        base_cursor.extend(["-f", prompt])
    else:
        base_agent.append(prompt)
        base_cursor.append(prompt)
    for cmd in [base_agent, base_cursor]:
        print("\nTrying:", " ".join(cmd[:3]) + " ...")
        print("cwd:", cwd)
        try:
            returncode, stdout, stderr = run_cli(cmd, cwd, env, timeout_sec)
            print("returncode:", returncode)
            if stdout:
                print("stdout:", stdout[:1500])
            if stderr:
                print("stderr:", stderr[:1500])
            if returncode == 0:
                if use_hello and (ROOT / "cursor_test_out" / "hello.py").exists():
                    print("\nSuccess: hello.py was created in cursor_test_out/")
                    print("Content:", (ROOT / "cursor_test_out" / "hello.py").read_text())
                else:
                    print("\nSuccess: Cursor CLI responded.")
                sys.exit(0)
        except FileNotFoundError:
            print("Command not found. Trying next invocation.")
            continue
        except subprocess.TimeoutExpired:
            print("Timed out after", timeout_sec, "seconds.")
            continue
        except Exception as e:
            print("Error:", type(e).__name__, e)
            continue

    print("\nCursor CLI did not succeed. Check that 'agent' or 'cursor' is on PATH and CURSOR_API_KEY is valid.")
    sys.exit(1)

if __name__ == "__main__":
    main()
