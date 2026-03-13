#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv

DOTENV = Path(".env")
load_dotenv(DOTENV)



# Flags that take a single path value right after them
_SINGLE_PATH_FLAGS = {
    "--refalleles", "-o", "--outpath", "--kraken_db", "--tmpdir", "--pathovar",
}
# Flags whose value may be comma-separated list of paths
_COMMA_PATH_FLAGS = {"-i", "--input"}

# Repo-relative defaults to inject if user didn't supply these flags
_REPO_DEFAULT_REFA = Path(f"species_specific_alleles/{os.getenv("APPNAME")}_intact_alleles.fasta")
_REPO_DEFAULT_PVK  = Path("mlst/mlst_pathovar_key.txt")

def _abspath_if_exists(p: str) -> str:
    ap = os.path.abspath(p)
    return ap if os.path.exists(ap) else p

def _flag_present(argv: list[str], flag_names: set[str]) -> bool:
    return any(f in argv for f in flag_names)

def _normalize_and_collect_mounts(argv: list[str]):
    """
    - Convert path-valued args to absolute host paths
    - Collect parent dirs to mount 1:1
    - Return (new_argv, mounts_set)
    """
    new_argv: list[str] = []
    mounts: set[str] = set()

    i = 0
    while i < len(argv):
        arg = argv[i]

        if arg in _SINGLE_PATH_FLAGS or arg in _COMMA_PATH_FLAGS:
            new_argv.append(arg)
            if i + 1 >= len(argv):
                break  # let downstream tool error cleanly
            val = argv[i + 1]

            if arg in _COMMA_PATH_FLAGS:
                parts = []
                for part in val.split(","):
                    part = part.strip()
                    ab = _abspath_if_exists(part)
                    if os.path.isdir(ab):
                        ab += '/'
                    parts.append(ab)
                    if os.path.exists(ab):
                        m = ab if os.path.isdir(ab) else os.path.dirname(ab)
                        if m:
                            mounts.add(m)
                    else:
                        sys.exit(f"No such file or directory: {part}")
                new_val = ",".join(parts)
            else:
                ab = _abspath_if_exists(val)
                if os.path.isdir(ab):
                    ab += '/'
                new_val = ab
                if os.path.exists(ab):
                    m = ab if os.path.isdir(ab) else os.path.dirname(ab)
                    if m:
                        mounts.add(m)
                else:
                    sys.exit(f"No such file or directory: {val}")

            new_argv.append(new_val)
            i += 2
            continue

        # Bare positional that looks like a path
        if not arg.startswith("-"):
            ab = _abspath_if_exists(arg)
            if os.path.exists(ab):
                m = ab if os.path.isdir(ab) else os.path.dirname(ab)
                if m:
                    mounts.add(m)
            new_argv.append(ab)
        else:
            new_argv.append(arg)

        i += 1

    return new_argv, mounts

def main():
    if not shutil.which("docker"):
        sys.stderr.write("Error: 'docker' not found in PATH.\n")
        sys.exit(1)
    try:
        subprocess.run(["docker", "compose", "version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        sys.stderr.write("Error: 'docker compose' not available.\n")
        sys.exit(1)

    try:
        uid = os.getuid(); gid = os.getgid()
    except AttributeError:
        sys.stderr.write("Error: os.getuid/os.getgid not available on this platform.\n")
        sys.exit(1)

    # Resolve repo root (two levels up from this script)
    wrapper_path = Path(__file__).resolve()
    repo_root = wrapper_path.parents[1]

    argv = sys.argv[1:]

    # If user omitted --refalleles, inject a repo default if it exists
    if "--refalleles" not in argv:
        candidate = (repo_root / _REPO_DEFAULT_REFA).resolve()
        if candidate.exists():
            argv += ["--refalleles", str(candidate)]
    # If user omitted --pathovar, inject a repo default if it exists
    if "--pathovar" not in argv:
        candidate = (repo_root / _REPO_DEFAULT_PVK).resolve()
        if candidate.exists():
            argv += ["--pathovar", str(candidate)]

    # Normalize paths and collect mounts
    norm_argv, mounts = _normalize_and_collect_mounts(argv)

    # Always mount the repo root and set workdir there
    mounts.add(str(repo_root))
    cmd = [
        "docker", "compose", "run", "--rm",
        "-e", f"UID={uid}",
        "-e", f"GID={gid}",
        "--user", f"{uid}:{gid}",
        "--workdir", str(repo_root),   # make relative paths behave like host
    ]
    for m in sorted(mounts):
        cmd += ["-v", f"{m}:{m}"]

    cmd.append("alleles")
    cmd += norm_argv

    try:
        sys.exit(subprocess.run(cmd).returncode)
    except FileNotFoundError:
        sys.stderr.write("Error: failed to execute docker command.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
