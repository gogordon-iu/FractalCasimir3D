#!/bin/bash
#SBATCH --job-name=fce_mver
#SBATCH --account=r01540
#SBATCH --partition=general
#SBATCH --mem=0
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=18
#SBATCH --cpus-per-task=7
#SBATCH --time=08:00:00
#SBATCH --array=1-12%4
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH --exclude=nid0394
#SBATCH --signal=B:SIGUSR1@120
#SBATCH -o logs/%x_%A_%a.out
#SBATCH -e logs/%x_%A_%a.err

# BIGRED200_TELEMETRY_HARNESS_V1
export http_proxy=http://proxy.uits.iu.edu:3128
export https_proxy=http://proxy.uits.iu.edu:3128
export no_proxy=localhost,127.0.0.1,*.iu.edu,*.uits.iu.edu
# SIGKILL/node loss cannot be trapped; publication is best-effort.
# Logs must exist BEFORE sbatch; the generator creates them locally.

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export WANDB_MODE=offline
export TORCH_HOME="${SLATE:-/N/slate/$USER}/.cache/torch"
case $- in
    *x*) BIGRED200_AUTH_XTRACE=1; set +x ;;
    *) BIGRED200_AUTH_XTRACE=0 ;;
esac
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    GITHUB_TOKEN="$(python3 - <<'BIGRED200_AUTH_PYTHON'
import os
from pathlib import Path
import re
import shlex
from typing import Optional
from urllib.parse import quote, unquote, urlsplit

def normalize_github_token(value):
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or any(character.isspace() or ord(character) < 32
                        or ord(character) == 127 for character in token):
        return None
    return token

def read_token_file(path):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            value = stream.read(65537)
        if len(value) > 65536:
            return None
        return normalize_github_token(value)
    except (OSError, UnicodeError, ValueError):
        return None

def github_cli_token(path):
    # Parse the small gh hosts.yml subset without an external YAML dependency.
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            source = stream.read(1048577)
        if len(source) > 1048576:
            return None
    except (OSError, UnicodeError, ValueError):
        return None
    host_indent = None
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if host_indent is not None and indent <= host_indent:
            host_indent = None
        if re.fullmatch(r"""(?:github\.com|'github\.com'|"github\.com"):\s*(?:#.*)?""",
                        stripped):
            host_indent = indent
            continue
        if host_indent is not None:
            match = re.fullmatch(r"oauth_token:[ \t]*(.*?)[ \t]*", stripped)
            if match:
                value = match.group(1)
                if value.startswith('"'):
                    import json
                    try:
                        value, _ = json.JSONDecoder().raw_decode(value)
                    except ValueError:
                        return None
                elif value.startswith("'"):
                    match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
                    if match is None:
                        return None
                    value = match.group(1).replace("''", "'")
                else:
                    value = re.split(r"\s+#", value, maxsplit=1)[0]
                return normalize_github_token(value)
    return None

def github_credentials_token(path):
    # Parse credential-store URLs directly; do not depend on Git's helper/PATH.
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            source = stream.read(1048577)
        if len(source) > 1048576:
            return None
    except (OSError, UnicodeError, ValueError):
        return None
    for line in source.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        try:
            url = urlsplit(value)
            # Match the actual host, not a substring in userinfo or a path.
            if url.scheme.lower() != "https" or url.hostname != "github.com":
                continue
            candidate = url.password or url.username
            if candidate is None:
                continue
            token = normalize_github_token(
                unquote(candidate, encoding="utf-8", errors="strict")
            )
        except (ValueError, UnicodeError):
            continue
        if token:
            return token
    return None

def discover_github_token() -> Optional[str]:
    for variable in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TOKEN"):
        token = normalize_github_token(os.environ.get(variable))
        if token:
            return token
    candidates = [Path.home() / ".github_token"]
    user = os.environ.get("USER", "")
    valid_user = bool(user and re.fullmatch(r"[A-Za-z0-9_.-]+", user))
    if valid_user:
        candidates.append(Path("/N/u") / user / ".github_token")
    slate = os.environ.get("SLATE")
    if slate:
        candidates.append(Path(slate) / ".github_token")
    for path in candidates:
        token = read_token_file(path)
        if token:
            return token
    token = github_cli_token(Path.home() / ".config" / "gh" / "hosts.yml")
    if token:
        return token
    credentials = [Path.home() / ".git-credentials"]
    if valid_user:
        credentials.extend((
            Path("/N/u") / user / ".git-credentials",
            Path("/N/u") / user / "BigRed200" / ".git-credentials",
        ))
    for path in credentials:
        token = github_credentials_token(path)
        if token:
            return token
    return None

def git_auth_environment(token=None):
    environment = dict(os.environ)
    environment.setdefault("GIT_AUTHOR_NAME", "BigRed200-JobRunner")
    environment.setdefault("GIT_AUTHOR_EMAIL", "bigred200@iu.edu")
    environment.setdefault("GIT_COMMITTER_NAME", "BigRed200-JobRunner")
    environment.setdefault("GIT_COMMITTER_EMAIL", "bigred200@iu.edu")
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_EDITOR"] = ":"
    environment["GIT_SEQUENCE_EDITOR"] = ":"
    token = normalize_github_token(token) or discover_github_token()
    settings = []
    if token:
        authenticated = "https://x-access-token:" + quote(token, safe="") + "@github.com/"
        # Equivalent to repeated `git -c url.<authenticated>.insteadOf=...`,
        # but keep the PAT out of argv/process listings and on-disk Git config.
        for original in ("https://github.com/", "git@github.com:",
                         "ssh://git@github.com/"):
            settings.append(("url." + authenticated + ".insteadOf", original))
    credentials = Path.home() / ".git-credentials"
    if credentials.is_file():
        settings.append(("credential.helper",
                         "store --file=" + shlex.quote(str(credentials))))
    if not token:
        for name in ("id_ed25519", "id_rsa"):
            key = Path.home() / ".ssh" / name
            if key.is_file():
                environment["GIT_SSH_COMMAND"] = (
                    "ssh -i " + shlex.quote(str(key))
                    + " -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
                )
                break
    try:
        count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        raise ValueError("Invalid GIT_CONFIG_COUNT")
    if count < 0:
        raise ValueError("Invalid GIT_CONFIG_COUNT")
    for key, value in settings:
        environment["GIT_CONFIG_KEY_" + str(count)] = key
        environment["GIT_CONFIG_VALUE_" + str(count)] = value
        count += 1
    environment["GIT_CONFIG_COUNT"] = str(count)
    return environment

def redact_git_output(value, environment=None):
    text = str(value)
    secrets = []
    for variable in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TOKEN"):
        token = normalize_github_token(os.environ.get(variable))
        if token:
            secrets.append(token)
    token = discover_github_token()
    if token:
        secrets.append(token)
    for secret in secrets:
        text = text.replace(quote(secret, safe=""), "[REDACTED]")
        text = text.replace(secret, "[REDACTED]")
    if environment:
        for key, value in environment.items():
            if key.startswith("GIT_CONFIG_KEY_") and "x-access-token:" in value:
                match = re.search(r"x-access-token:([^@]+)@", value)
                if match:
                    text = text.replace(match.group(1), "[REDACTED]")
    return re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)

def git_authentication_failed(result):
    output = (result.stderr or "") + "\n" + (result.stdout or "")
    return bool(re.search(
        r"could not read Username|Authentication failed|Permission denied"
        r"|write access.*not granted|requested URL returned error: (?:401|403)",
        output, re.IGNORECASE,
    ))

AUTHORIZATION_DIAGNOSTIC = (
    "Remote Git push failed due to missing write authorization. "
    "Run 'setup-auth --token <PAT>' on the login node or save your token "
    "to ~/.github_token."
)
print(discover_github_token() or "")
BIGRED200_AUTH_PYTHON
    )" || GITHUB_TOKEN=""
    export GITHUB_TOKEN
fi
if [[ -z "${GITHUB_TOKEN:-}" && -n "${HOME:-}" && -f "$HOME/.git-credentials" ]]; then
    GITHUB_TOKEN="$(python3 - <<'BIGRED200_CREDENTIALS_PYTHON'
import os
from pathlib import Path
import re
import shlex
from typing import Optional
from urllib.parse import quote, unquote, urlsplit

def normalize_github_token(value):
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or any(character.isspace() or ord(character) < 32
                        or ord(character) == 127 for character in token):
        return None
    return token

def read_token_file(path):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            value = stream.read(65537)
        if len(value) > 65536:
            return None
        return normalize_github_token(value)
    except (OSError, UnicodeError, ValueError):
        return None

def github_cli_token(path):
    # Parse the small gh hosts.yml subset without an external YAML dependency.
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            source = stream.read(1048577)
        if len(source) > 1048576:
            return None
    except (OSError, UnicodeError, ValueError):
        return None
    host_indent = None
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if host_indent is not None and indent <= host_indent:
            host_indent = None
        if re.fullmatch(r"""(?:github\.com|'github\.com'|"github\.com"):\s*(?:#.*)?""",
                        stripped):
            host_indent = indent
            continue
        if host_indent is not None:
            match = re.fullmatch(r"oauth_token:[ \t]*(.*?)[ \t]*", stripped)
            if match:
                value = match.group(1)
                if value.startswith('"'):
                    import json
                    try:
                        value, _ = json.JSONDecoder().raw_decode(value)
                    except ValueError:
                        return None
                elif value.startswith("'"):
                    match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
                    if match is None:
                        return None
                    value = match.group(1).replace("''", "'")
                else:
                    value = re.split(r"\s+#", value, maxsplit=1)[0]
                return normalize_github_token(value)
    return None

def github_credentials_token(path):
    # Parse credential-store URLs directly; do not depend on Git's helper/PATH.
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            source = stream.read(1048577)
        if len(source) > 1048576:
            return None
    except (OSError, UnicodeError, ValueError):
        return None
    for line in source.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        try:
            url = urlsplit(value)
            # Match the actual host, not a substring in userinfo or a path.
            if url.scheme.lower() != "https" or url.hostname != "github.com":
                continue
            candidate = url.password or url.username
            if candidate is None:
                continue
            token = normalize_github_token(
                unquote(candidate, encoding="utf-8", errors="strict")
            )
        except (ValueError, UnicodeError):
            continue
        if token:
            return token
    return None

def discover_github_token() -> Optional[str]:
    for variable in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TOKEN"):
        token = normalize_github_token(os.environ.get(variable))
        if token:
            return token
    candidates = [Path.home() / ".github_token"]
    user = os.environ.get("USER", "")
    valid_user = bool(user and re.fullmatch(r"[A-Za-z0-9_.-]+", user))
    if valid_user:
        candidates.append(Path("/N/u") / user / ".github_token")
    slate = os.environ.get("SLATE")
    if slate:
        candidates.append(Path(slate) / ".github_token")
    for path in candidates:
        token = read_token_file(path)
        if token:
            return token
    token = github_cli_token(Path.home() / ".config" / "gh" / "hosts.yml")
    if token:
        return token
    credentials = [Path.home() / ".git-credentials"]
    if valid_user:
        credentials.extend((
            Path("/N/u") / user / ".git-credentials",
            Path("/N/u") / user / "BigRed200" / ".git-credentials",
        ))
    for path in credentials:
        token = github_credentials_token(path)
        if token:
            return token
    return None

def git_auth_environment(token=None):
    environment = dict(os.environ)
    environment.setdefault("GIT_AUTHOR_NAME", "BigRed200-JobRunner")
    environment.setdefault("GIT_AUTHOR_EMAIL", "bigred200@iu.edu")
    environment.setdefault("GIT_COMMITTER_NAME", "BigRed200-JobRunner")
    environment.setdefault("GIT_COMMITTER_EMAIL", "bigred200@iu.edu")
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_EDITOR"] = ":"
    environment["GIT_SEQUENCE_EDITOR"] = ":"
    token = normalize_github_token(token) or discover_github_token()
    settings = []
    if token:
        authenticated = "https://x-access-token:" + quote(token, safe="") + "@github.com/"
        # Equivalent to repeated `git -c url.<authenticated>.insteadOf=...`,
        # but keep the PAT out of argv/process listings and on-disk Git config.
        for original in ("https://github.com/", "git@github.com:",
                         "ssh://git@github.com/"):
            settings.append(("url." + authenticated + ".insteadOf", original))
    credentials = Path.home() / ".git-credentials"
    if credentials.is_file():
        settings.append(("credential.helper",
                         "store --file=" + shlex.quote(str(credentials))))
    if not token:
        for name in ("id_ed25519", "id_rsa"):
            key = Path.home() / ".ssh" / name
            if key.is_file():
                environment["GIT_SSH_COMMAND"] = (
                    "ssh -i " + shlex.quote(str(key))
                    + " -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
                )
                break
    try:
        count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        raise ValueError("Invalid GIT_CONFIG_COUNT")
    if count < 0:
        raise ValueError("Invalid GIT_CONFIG_COUNT")
    for key, value in settings:
        environment["GIT_CONFIG_KEY_" + str(count)] = key
        environment["GIT_CONFIG_VALUE_" + str(count)] = value
        count += 1
    environment["GIT_CONFIG_COUNT"] = str(count)
    return environment

def redact_git_output(value, environment=None):
    text = str(value)
    secrets = []
    for variable in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TOKEN"):
        token = normalize_github_token(os.environ.get(variable))
        if token:
            secrets.append(token)
    token = discover_github_token()
    if token:
        secrets.append(token)
    for secret in secrets:
        text = text.replace(quote(secret, safe=""), "[REDACTED]")
        text = text.replace(secret, "[REDACTED]")
    if environment:
        for key, value in environment.items():
            if key.startswith("GIT_CONFIG_KEY_") and "x-access-token:" in value:
                match = re.search(r"x-access-token:([^@]+)@", value)
                if match:
                    text = text.replace(match.group(1), "[REDACTED]")
    return re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)

def git_authentication_failed(result):
    output = (result.stderr or "") + "\n" + (result.stdout or "")
    return bool(re.search(
        r"could not read Username|Authentication failed|Permission denied"
        r"|write access.*not granted|requested URL returned error: (?:401|403)",
        output, re.IGNORECASE,
    ))

AUTHORIZATION_DIAGNOSTIC = (
    "Remote Git push failed due to missing write authorization. "
    "Run 'setup-auth --token <PAT>' on the login node or save your token "
    "to ~/.github_token."
)
print(github_credentials_token(Path(os.environ["HOME"]) / ".git-credentials") or "")
BIGRED200_CREDENTIALS_PYTHON
    )" || GITHUB_TOKEN=""
    if [[ -n "$GITHUB_TOKEN" ]]; then
        export GITHUB_TOKEN
    fi
fi
if [[ "$BIGRED200_AUTH_XTRACE" == "1" ]]; then set -x; fi
unset BIGRED200_AUTH_XTRACE
export JOB_START_TIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TERMINATION_REASON="UNEXPECTED_EXIT"
CHILD_PID=""

resubmit_job() {
    echo "[BigRed200] Registering job continuation/resubmission..."
    touch -- "${SLURM_SUBMIT_DIR:-$PWD}/.resubmit_${SLURM_JOB_ID:-local}" || return $?
    export RESUBMITTED=1
    if [[ $# -gt 0 ]]; then
        sbatch "$@"
    fi
}
export -f resubmit_job 2>/dev/null || true

terminate_child_group() {
    if [[ -n "${CHILD_PID:-}" ]]; then
        kill -15 -- "-${CHILD_PID}" 2>/dev/null || true
    fi
}

handle_job_exit() {
    local EXIT_CODE=$?
    if [[ $# -gt 0 ]]; then EXIT_CODE="$1"; fi
    trap - EXIT ERR SIGTERM SIGINT SIGUSR1
    set +e
    terminate_child_group
    sync || true
    if [[ "$TERMINATION_REASON" == "SLURM_WALLTIME_TIMEOUT" ]]; then
        EXIT_CODE=124
    fi
    if [[ -f "${SLURM_SUBMIT_DIR:-$PWD}/.resubmit_${SLURM_JOB_ID:-local}"
          || -e "${SLURM_SUBMIT_DIR:-$PWD}/.slurm_resubmitted"
          || "${RESUBMITTED:-0}" == "1"
          || "${SLURM_JOB_RESUBMITTED:-0}" == "1"
          || "$EXIT_CODE" -eq 99
          || "$TERMINATION_REASON" == "RESUBMITTED"
          || "$TERMINATION_REASON" == "JOB_CHAINED"
          || "$TERMINATION_REASON" == "REQUEUED" ]]; then
        TERMINATION_REASON="RESUBMITTED"
        if [[ "$EXIT_CODE" -ne 124 ]]; then
            EXIT_CODE=0
        fi
    fi
    if [[ "$TERMINATION_REASON" != "RESUBMITTED" ]]; then
        (
            git config user.name >/dev/null 2>&1 || git config user.name "BigRed200-JobRunner"
            git config user.email >/dev/null 2>&1 || git config user.email "bigred200@iu.edu"
            CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
            export CURRENT_BRANCH
        )
    fi
    python3 - "$EXIT_CODE" "$TERMINATION_REASON" <<'BIGRED200_TELEMETRY_PYTHON'
import os
from pathlib import Path
import re
import shlex
from typing import Optional
from urllib.parse import quote, unquote, urlsplit

def normalize_github_token(value):
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or any(character.isspace() or ord(character) < 32
                        or ord(character) == 127 for character in token):
        return None
    return token

def read_token_file(path):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            value = stream.read(65537)
        if len(value) > 65536:
            return None
        return normalize_github_token(value)
    except (OSError, UnicodeError, ValueError):
        return None

def github_cli_token(path):
    # Parse the small gh hosts.yml subset without an external YAML dependency.
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            source = stream.read(1048577)
        if len(source) > 1048576:
            return None
    except (OSError, UnicodeError, ValueError):
        return None
    host_indent = None
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if host_indent is not None and indent <= host_indent:
            host_indent = None
        if re.fullmatch(r"""(?:github\.com|'github\.com'|"github\.com"):\s*(?:#.*)?""",
                        stripped):
            host_indent = indent
            continue
        if host_indent is not None:
            match = re.fullmatch(r"oauth_token:[ \t]*(.*?)[ \t]*", stripped)
            if match:
                value = match.group(1)
                if value.startswith('"'):
                    import json
                    try:
                        value, _ = json.JSONDecoder().raw_decode(value)
                    except ValueError:
                        return None
                elif value.startswith("'"):
                    match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
                    if match is None:
                        return None
                    value = match.group(1).replace("''", "'")
                else:
                    value = re.split(r"\s+#", value, maxsplit=1)[0]
                return normalize_github_token(value)
    return None

def github_credentials_token(path):
    # Parse credential-store URLs directly; do not depend on Git's helper/PATH.
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            source = stream.read(1048577)
        if len(source) > 1048576:
            return None
    except (OSError, UnicodeError, ValueError):
        return None
    for line in source.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        try:
            url = urlsplit(value)
            # Match the actual host, not a substring in userinfo or a path.
            if url.scheme.lower() != "https" or url.hostname != "github.com":
                continue
            candidate = url.password or url.username
            if candidate is None:
                continue
            token = normalize_github_token(
                unquote(candidate, encoding="utf-8", errors="strict")
            )
        except (ValueError, UnicodeError):
            continue
        if token:
            return token
    return None

def discover_github_token() -> Optional[str]:
    for variable in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TOKEN"):
        token = normalize_github_token(os.environ.get(variable))
        if token:
            return token
    candidates = [Path.home() / ".github_token"]
    user = os.environ.get("USER", "")
    valid_user = bool(user and re.fullmatch(r"[A-Za-z0-9_.-]+", user))
    if valid_user:
        candidates.append(Path("/N/u") / user / ".github_token")
    slate = os.environ.get("SLATE")
    if slate:
        candidates.append(Path(slate) / ".github_token")
    for path in candidates:
        token = read_token_file(path)
        if token:
            return token
    token = github_cli_token(Path.home() / ".config" / "gh" / "hosts.yml")
    if token:
        return token
    credentials = [Path.home() / ".git-credentials"]
    if valid_user:
        credentials.extend((
            Path("/N/u") / user / ".git-credentials",
            Path("/N/u") / user / "BigRed200" / ".git-credentials",
        ))
    for path in credentials:
        token = github_credentials_token(path)
        if token:
            return token
    return None

def git_auth_environment(token=None):
    environment = dict(os.environ)
    environment.setdefault("GIT_AUTHOR_NAME", "BigRed200-JobRunner")
    environment.setdefault("GIT_AUTHOR_EMAIL", "bigred200@iu.edu")
    environment.setdefault("GIT_COMMITTER_NAME", "BigRed200-JobRunner")
    environment.setdefault("GIT_COMMITTER_EMAIL", "bigred200@iu.edu")
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_EDITOR"] = ":"
    environment["GIT_SEQUENCE_EDITOR"] = ":"
    token = normalize_github_token(token) or discover_github_token()
    settings = []
    if token:
        authenticated = "https://x-access-token:" + quote(token, safe="") + "@github.com/"
        # Equivalent to repeated `git -c url.<authenticated>.insteadOf=...`,
        # but keep the PAT out of argv/process listings and on-disk Git config.
        for original in ("https://github.com/", "git@github.com:",
                         "ssh://git@github.com/"):
            settings.append(("url." + authenticated + ".insteadOf", original))
    credentials = Path.home() / ".git-credentials"
    if credentials.is_file():
        settings.append(("credential.helper",
                         "store --file=" + shlex.quote(str(credentials))))
    if not token:
        for name in ("id_ed25519", "id_rsa"):
            key = Path.home() / ".ssh" / name
            if key.is_file():
                environment["GIT_SSH_COMMAND"] = (
                    "ssh -i " + shlex.quote(str(key))
                    + " -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
                )
                break
    try:
        count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        raise ValueError("Invalid GIT_CONFIG_COUNT")
    if count < 0:
        raise ValueError("Invalid GIT_CONFIG_COUNT")
    for key, value in settings:
        environment["GIT_CONFIG_KEY_" + str(count)] = key
        environment["GIT_CONFIG_VALUE_" + str(count)] = value
        count += 1
    environment["GIT_CONFIG_COUNT"] = str(count)
    return environment

def redact_git_output(value, environment=None):
    text = str(value)
    secrets = []
    for variable in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TOKEN"):
        token = normalize_github_token(os.environ.get(variable))
        if token:
            secrets.append(token)
    token = discover_github_token()
    if token:
        secrets.append(token)
    for secret in secrets:
        text = text.replace(quote(secret, safe=""), "[REDACTED]")
        text = text.replace(secret, "[REDACTED]")
    if environment:
        for key, value in environment.items():
            if key.startswith("GIT_CONFIG_KEY_") and "x-access-token:" in value:
                match = re.search(r"x-access-token:([^@]+)@", value)
                if match:
                    text = text.replace(match.group(1), "[REDACTED]")
    return re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)

def git_authentication_failed(result):
    output = (result.stderr or "") + "\n" + (result.stdout or "")
    return bool(re.search(
        r"could not read Username|Authentication failed|Permission denied"
        r"|write access.*not granted|requested URL returned error: (?:401|403)",
        output, re.IGNORECASE,
    ))

AUTHORIZATION_DIAGNOSTIC = (
    "Remote Git push failed due to missing write authorization. "
    "Run 'setup-auth --token <PAT>' on the login node or save your token "
    "to ~/.github_token."
)

import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

CONFIG = json.loads('{"auto_resubmit": "0", "figures_dir": "figures", "git_remote": "origin", "logs_dir": "logs", "results_dir": "results_nature_meep_verification", "strict_telemetry": "0"}')
BLOCKED_SUFFIXES = (".pt", ".ckpt", ".bin", ".h5", ".safetensors", ".tar")
MAX_GIT_FILE_BYTES = 50 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 45
SYNC_FAILURE_NOTICE = (
    "NOTICE: Workload completed successfully (exit 0), but remote Git sync "
    "failed. All results and logs are safely preserved on cluster disk."
)

def diagnostic(message):
    print("[BigRed200 telemetry] " + str(message), file=sys.stderr, flush=True)

def run(command, check=True):
    environment = git_auth_environment()
    result = subprocess.run(
        command, cwd=str(ROOT), env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace", timeout=GIT_TIMEOUT_SECONDS,
    )
    result.stdout = redact_git_output(result.stdout, environment)
    result.stderr = redact_git_output(result.stderr, environment)
    if check and result.returncode != 0:
        raise RuntimeError(
            "{} failed ({}): {}".format(
                command[0:2], result.returncode,
                (result.stderr or result.stdout).strip()[-6000:],
            )
        )
    return result

def git(arguments, check=True):
    return run(["git"] + arguments, check=check)

def abort_rebase():
    # A failed pull may not have started a rebase; abort is still attempted.
    aborted = git(["rebase", "--abort"], check=False)
    git_directory = Path(git(["rev-parse", "--absolute-git-dir"]).stdout.strip())
    if (git_directory / "rebase-merge").exists() or (git_directory / "rebase-apply").exists():
        raise RuntimeError(
            "Could not abort failed rebase; resolve manually before synchronization: "
            + (aborted.stderr or aborted.stdout).strip()[-3000:]
        )

def remote_git(arguments, rebase=False):
    # Three bounded attempts, including timeout/network exceptions.
    for attempt in range(3):
        result = None
        error = None
        try:
            result = git(arguments, check=False)
        except (OSError, subprocess.SubprocessError) as caught:
            error = caught
        finally:
            if rebase and (result is None or result.returncode != 0):
                # Recover immediately, before sleeping, retrying, or pushing.
                abort_rebase()
        if result is not None and result.returncode == 0:
            return result
        if attempt == 2:
            if error is not None:
                raise error
            return result
        delay = (2, 5)[attempt]
        detail = redact_git_output(error) if error is not None else (
            result.stderr or result.stdout
        ).strip()[-3000:]
        diagnostic(
            "git {} attempt {} failed; retrying in {}s: {}".format(
                arguments[0], attempt + 1, delay, detail
            )
        )
        time.sleep(delay)

def safe_path(relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("Unsafe repository-relative path: " + str(relative))
    current = ROOT
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Refusing symlink path: " + str(current))
    resolved = current.resolve()
    if resolved != ROOT and ROOT not in resolved.parents:
        raise ValueError("Path escapes repository: " + str(relative))
    if ".git" in path.parts:
        raise ValueError("Refusing Git metadata path")
    return current

def safe_file(path):
    if path.is_symlink() or not path.is_file():
        return False
    relative = path.relative_to(ROOT)
    safe_path(str(relative))
    # Exclude checkpoints even when compression/other suffixes are appended.
    if any(suffix.lower() in BLOCKED_SUFFIXES for suffix in path.suffixes):
        return False
    size = path.stat().st_size
    if size > MAX_GIT_FILE_BYTES:
        diagnostic(
            "Skipping oversized file for Git staging: {} ({} bytes; limit {} bytes).".format(
                relative, size, MAX_GIT_FILE_BYTES
            )
        )
        return False
    return True

def collect(directory):
    base = safe_path(directory)
    files = []
    if not base.exists():
        return files
    if not base.is_dir():
        raise ValueError("Expected directory: " + str(base))
    for current, directories, names in os.walk(str(base), followlinks=False):
        parent = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name != ".git" and not (parent / name).is_symlink()
        )
        for name in sorted(names):
            path = parent / name
            if safe_file(path):
                files.append(str(path.relative_to(ROOT)))
    return files

def outputs_verified(directory):
    base = safe_path(directory)
    if not base.is_dir():
        return False
    for current, directories, names in os.walk(str(base), followlinks=False):
        parent = Path(current)
        directories[:] = [
            name for name in directories
            if name != ".git" and not (parent / name).is_symlink()
        ]
        for name in names:
            path = parent / name
            if not path.is_symlink() and path.is_file() and path.stat().st_size > 0:
                return True
    return False

def write_report(report):
    array_job_id = os.environ.get("SLURM_ARRAY_JOB_ID", "")
    array_task_id = os.environ.get("SLURM_ARRAY_TASK_ID", "")
    report_id = JOB_ID
    if (
        array_job_id and array_task_id
        and all(c.isalnum() or c in "_.-" for c in array_job_id)
        and all(c.isalnum() or c in "_.-" for c in array_task_id)
    ):
        report_id = array_job_id + "_" + array_task_id
    destination = safe_path(CONFIG["logs_dir"]) / ("crash_report_" + report_id + ".json")
    if destination.is_symlink():
        raise ValueError("Refusing symlink crash report")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp." + str(os.getpid()))
    descriptor = os.open(
        str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(destination))
    finally:
        if temporary.exists():
            temporary.unlink()
    return str(destination.relative_to(ROOT))

def publish(paths, message):
    selected = []
    for relative in sorted(set(paths)):
        path = safe_path(relative)
        if not path.is_symlink() and path.is_file():
            size = path.stat().st_size
            if size > MAX_GIT_FILE_BYTES:
                diagnostic(
                    "Skipping oversized file for Git staging: {} ({} bytes; limit {} bytes).".format(
                        relative, size, MAX_GIT_FILE_BYTES
                    )
                )
                continue
        if not safe_file(path):
            raise ValueError("Unsafe staging candidate: " + relative)
        selected.append(relative)

    git_directory_value = git(["rev-parse", "--git-dir"]).stdout.strip()
    if not git_directory_value:
        raise RuntimeError("Git returned an empty Git directory")
    git_directory = Path(git_directory_value)
    if not git_directory.is_absolute():
        git_directory = ROOT / git_directory
    git_directory = git_directory.resolve(strict=True)
    if not git_directory.is_dir():
        raise RuntimeError("Expected Git directory: " + str(git_directory))

    lock_path = git_directory / "bigred200_telemetry.lock"
    if lock_path.is_symlink():
        raise ValueError("Refusing symlink telemetry lock: " + str(lock_path))
    # Keep the lock file in place so all tasks lock the same inode.
    with lock_path.open("a") as lock_stream:
        deadline = time.monotonic() + 120
        while True:
            try:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for telemetry Git lock")
                time.sleep(min(0.5, remaining))
        try:
            return publish_locked(selected, message, git_directory)
        finally:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)

def publish_locked(selected, message, git_directory):
    for lock_name in ("index.lock", "config.lock"):
        lock = git_directory / lock_name
        try:
            if lock.is_symlink():
                raise ValueError("Refusing symlink Git lock: " + str(lock))
            if lock.exists():
                if not lock.is_file():
                    raise ValueError("Refusing non-regular Git lock: " + str(lock))
                lock.unlink()
                diagnostic("Removed stale Git lock: " + str(lock))
        except FileNotFoundError:
            pass
    initial_head = git(["rev-parse", "HEAD"]).stdout.strip()

    git(["config", "user.name"], check=False)
    if git(["config", "--get", "user.name"], check=False).returncode != 0:
        git(["config", "user.name", "BigRed200-JobRunner"])
    if git(["config", "--get", "user.email"], check=False).returncode != 0:
        git(["config", "user.email", "bigred200@iu.edu"])

    branch = git(["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    if branch.returncode != 0 or not branch.stdout.strip():
        raise RuntimeError("Detached HEAD: refusing to guess a push branch")
    current_branch = branch.stdout.strip()
    git(["check-ref-format", "--branch", current_branch])
    git(["remote", "get-url", "--", CONFIG["git_remote"]])

    # Unstage unrelated changes without modifying their working-tree contents.
    staged = git(["diff", "--cached", "--name-only", "-z"]).stdout
    unrelated = sorted(set(name for name in staged.split("\0") if name) - set(selected))
    if unrelated:
        for offset in range(0, len(unrelated), 100):
            git(["reset", "HEAD", "--"] + unrelated[offset:offset + 100])
        diagnostic("Unstaged unrelated changes; working-tree files were preserved.")

    # Stage only enumerated files; never recursively `git add` a directory.
    # -f permits required diagnostics in repositories that ignore logs/results.
    for offset in range(0, len(selected), 100):
        git(["add", "-f", "--"] + selected[offset:offset + 100])

    staged = git(["diff", "--cached", "--name-only", "-z"]).stdout
    staged_paths = [name for name in staged.split("\0") if name]
    # Retain the safety check against concurrently staged unrelated changes.
    if set(staged_paths) - set(selected):
        raise RuntimeError("Unrelated changes were staged during telemetry publication")
    for relative in staged_paths:
        if any(s.lower() in BLOCKED_SUFFIXES for s in Path(relative).suffixes):
            raise RuntimeError("Checkpoint staging safety violation: " + relative)
        staged_size = int(git(["cat-file", "-s", ":" + relative]).stdout.strip())
        if staged_size > MAX_GIT_FILE_BYTES:
            git(["reset", "HEAD", "--", relative])
            diagnostic(
                "Skipping oversized staged file: {} ({} bytes; limit {} bytes).".format(
                    relative, staged_size, MAX_GIT_FILE_BYTES
                )
            )
    staged = git(["diff", "--cached", "--name-only", "-z"]).stdout
    staged_paths = [name for name in staged.split("\0") if name]
    if set(staged_paths) - set(selected):
        raise RuntimeError("Unrelated changes were staged during telemetry publication")

    new_commit_created = False
    if staged_paths:
        committed = git(["commit", "-m", message], check=False)
        current_head = git(["rev-parse", "HEAD"]).stdout.strip()
        if current_head == initial_head:
            diagnostic(
                "git commit did not advance HEAD; creating telemetry commit with Git plumbing: "
                + (committed.stderr or committed.stdout).strip()[-3000:]
            )
            # Hooks may have changed the index; recheck before the fallback.
            fallback_staged = git(["diff", "--cached", "--name-only", "-z"]).stdout
            fallback_paths = [name for name in fallback_staged.split("\0") if name]
            if set(fallback_paths) - set(selected):
                raise RuntimeError("Unrelated changes were staged during commit fallback")
            for relative in fallback_paths:
                if any(s.lower() in BLOCKED_SUFFIXES for s in Path(relative).suffixes):
                    raise RuntimeError("Checkpoint staging safety violation: " + relative)
                staged_size = int(git(["cat-file", "-s", ":" + relative]).stdout.strip())
                if staged_size > MAX_GIT_FILE_BYTES:
                    raise RuntimeError("Oversized staging candidate during commit fallback: " + relative)
            tree = git(["write-tree"]).stdout.strip()
            current_head = git([
                "commit-tree", tree, "-p", initial_head, "-m", message,
            ]).stdout.strip()
            if not current_head or current_head == initial_head:
                raise RuntimeError("Commit fallback did not create a new commit")
            # Compare-and-swap prevents overwriting a concurrently advanced HEAD.
            git(["update-ref", "HEAD", current_head, initial_head])
        new_commit_created = current_head != initial_head
    else:
        diagnostic("No new safe changes to commit; attempting synchronization.")

    # Autostash permits rebase while other array tasks have unstaged outputs.
    try:
        pulled = remote_git(
            ["pull", "--rebase", "--autostash", CONFIG["git_remote"], current_branch],
            rebase=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        diagnostic("git pull --rebase failed: " + redact_git_output(error))
    else:
        if pulled.returncode != 0:
            diagnostic(
                "git pull --rebase failed: "
                + (pulled.stderr or pulled.stdout).strip()[-3000:]
            )

    pushed = remote_git(["push", CONFIG["git_remote"], current_branch])
    if pushed.returncode != 0:
        output = (pushed.stderr or "") + "\n" + (pushed.stdout or "")
        detail = output.strip()[-6000:]
        if re.search(
            r"non-fast-forward|fetch first|remote contains work"
            r"|diverg(?:ed|ence|ent)|tip of your current branch is behind",
            output, re.IGNORECASE,
        ):
            current_head = git(["rev-parse", "HEAD"]).stdout.strip()
            if not new_commit_created or not current_head or current_head == initial_head:
                raise RuntimeError(
                    "Refusing fallback push without a new telemetry commit: " + detail
                )
            fallback_branch = f"telemetry/job-{JOB_ID}"
            git(["check-ref-format", "refs/heads/" + fallback_branch])
            fallback = remote_git([
                "push", CONFIG["git_remote"],
                f"{current_head}:refs/heads/{fallback_branch}",
            ])
            if fallback.returncode == 0:
                diagnostic(
                    "Pushed results to fallback branch '{}' due to divergence on '{}'.".format(
                        fallback_branch, current_branch
                    )
                )
                return
            fallback_detail = (fallback.stderr or fallback.stdout).strip()[-6000:]
            if git_authentication_failed(fallback):
                raise RuntimeError(AUTHORIZATION_DIAGNOSTIC + "\n" + fallback_detail)
            raise RuntimeError(
                "git push failed on '{}' and fallback '{}': {}\n{}".format(
                    current_branch, fallback_branch, detail, fallback_detail
                )
            )
        if git_authentication_failed(pushed):
            raise RuntimeError(AUTHORIZATION_DIAGNOSTIC + "\n" + detail)
        raise RuntimeError("git push failed ({}): {}".format(pushed.returncode, detail))

def continuation_detected(code, reason):
    submit_directory = Path(os.environ.get("SLURM_SUBMIT_DIR") or str(ROOT)).resolve()
    sentinel_job_id = os.environ.get("SLURM_JOB_ID") or "local"
    sentinels = (
        submit_directory / (".resubmit_" + sentinel_job_id),
        submit_directory / ".slurm_resubmitted",
    )
    continuing = (
        reason in ("RESUBMITTED", "JOB_CHAINED", "REQUEUED")
        or code == 99
        or os.environ.get("RESUBMITTED") == "1"
        or os.environ.get("SLURM_JOB_RESUBMITTED") == "1"
        or any(path.exists() for path in sentinels)
    )
    if not continuing:
        return False
    diagnostic(
        "Job resubmitted/chained (task continuing). "
        "Skipping Git commit, push, and crash reporting."
    )
    for path in sentinels:
        try:
            # unlink never follows a symlink or recursively removes a directory.
            if path.is_symlink() or path.is_file():
                path.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            diagnostic("Could not remove continuation sentinel: " + str(error))
    return True

def main():
    global ROOT, JOB_ID
    ROOT = Path.cwd().resolve()
    JOB_ID = os.environ.get("SLURM_JOB_ID", "local_" + str(os.getppid()))
    if not JOB_ID or not all(c.isalnum() or c in "_.-" for c in JOB_ID):
        raise ValueError("Unsafe SLURM_JOB_ID")

    code = int(sys.argv[1])
    reason = sys.argv[2]
    if code < 0 or code > 255:
        raise ValueError("Exit code outside shell range")
    if continuation_detected(code, reason):
        return 0

    name = os.environ.get("SLURM_JOB_NAME", "proj_job")
    if "/" in name or "\\" in name or "\0" in name:
        raise ValueError("Unsafe SLURM_JOB_NAME")

    logs = safe_path(CONFIG["logs_dir"])
    logs.mkdir(parents=True, exist_ok=True)
    array_job_id = os.environ.get("SLURM_ARRAY_JOB_ID")
    array_task_id = os.environ.get("SLURM_ARRAY_TASK_ID")
    if array_job_id and array_task_id:
        stdout_log = logs / f"{name}_{array_job_id}_{array_task_id}.out"
        stderr_log = logs / f"{name}_{array_job_id}_{array_task_id}.err"
        if not stdout_log.exists():
            stdout_log = logs / (name + "_" + JOB_ID + ".out")
        if not stderr_log.exists():
            stderr_log = logs / (name + "_" + JOB_ID + ".err")
    else:
        stdout_log = logs / (name + "_" + JOB_ID + ".out")
        stderr_log = logs / (name + "_" + JOB_ID + ".err")
    verified = outputs_verified(CONFIG["results_dir"])
    if code == 0 and not verified:
        code = 66
        reason = "MISSING_OR_EMPTY_OUTPUTS"
    elif code == 0:
        reason = "SUCCESS"
    elif reason == "UNEXPECTED_EXIT":
        reason = "NONZERO_EXIT"

    report = {
        "schema_version": 1,
        "job_id": JOB_ID,
        "job_name": name,
        "exit_code": code,
        "termination_reason": reason,
        "started_at": os.environ.get("JOB_START_TIME", ""),
        "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": os.uname().nodename,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "results_dir": str(safe_path(CONFIG["results_dir"])),
        "outputs_verified": verified,
        "slurm": {
            key: os.environ.get(key, "")
            for key in (
                "SLURM_JOB_ID", "SLURM_JOB_NAME", "SLURM_JOB_NODELIST",
                "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID", "SLURM_SUBMIT_DIR",
            )
        },
        "telemetry_errors": [],
    }

    try:
        paths = []
        if code == 0:
            paths.extend(collect(CONFIG["results_dir"]))
            paths.extend(collect(CONFIG["figures_dir"]))
            paths.extend(collect(CONFIG["logs_dir"]))
            if safe_path("results").exists():
                paths.extend(collect("results"))
            if safe_path("results_clutch_pilot").exists():
                paths.extend(collect("results_clutch_pilot"))
            message = "[BigRed200] SUCCESS: Job {} ({}) on {}".format(
                JOB_ID, name, report["hostname"]
            )
        else:
            paths.append(write_report(report))
            message = "[BigRed200] FAILED: Job {} ({}) exit code {} [{}]".format(
                JOB_ID, name, code, reason
            )
        for log in (stdout_log, stderr_log):
            if safe_file(log):
                paths.append(str(log.relative_to(ROOT)))

        repository = Path(git(["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
        if repository != ROOT:
            raise RuntimeError("Submit from the repository root, not a subdirectory")
        publish(paths, message)
    except Exception as error:
        safe_error = redact_git_output(error)
        diagnostic(safe_error)
        report["telemetry_errors"].append(safe_error)
        report["telemetry_status"] = "TELEMETRY_SYNC_FAILED"
        if code == 0:
            diagnostic(SYNC_FAILURE_NOTICE)
            if CONFIG.get("strict_telemetry", "0") == "1":
                code = 74
                report["exit_code"] = code
                report["termination_reason"] = "TELEMETRY_FAILURE"
        report["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            write_report(report)
        except Exception as report_error:
            diagnostic("Could not persist telemetry failure: " + redact_git_output(report_error))
    return code

try:
    sys.exit(main())
except Exception as error:
    diagnostic("Fatal telemetry error: " + redact_git_output(error))
    # Even failures before report construction must not poison workload success.
    try:
        original_code = int(sys.argv[1])
        if not 0 <= original_code <= 255:
            original_code = 1
    except (IndexError, ValueError):
        original_code = 1
    if original_code == 0:
        diagnostic(SYNC_FAILURE_NOTICE)
        if CONFIG.get("strict_telemetry", "0") == "1":
            original_code = 74
    sys.exit(original_code)
BIGRED200_TELEMETRY_PYTHON
    local TELEMETRY_CODE=$?
    if [[ "$EXIT_CODE" -eq 0 ]]; then
        if [[ "$TELEMETRY_CODE" -eq 66 || ( "0" == "1" && "$TELEMETRY_CODE" -ne 0 ) ]]; then
            EXIT_CODE="$TELEMETRY_CODE"
        fi
    fi
    exit "$EXIT_CODE"
}

handle_walltime() {
    TERMINATION_REASON="SLURM_WALLTIME_TIMEOUT"
    printf "%s\n" "[BigRed200] Walltime warning; terminating workload." >&2
    terminate_child_group
    exit 124
}

trap 'handle_job_exit' EXIT ERR
trap 'TERMINATION_REASON="SLURM_CANCELLED"; handle_job_exit 143' SIGTERM
trap 'TERMINATION_REASON="SIGINT"; handle_job_exit 130' SIGINT
trap 'handle_walltime' SIGUSR1
set -Eeuo pipefail
cd -- "${SLURM_SUBMIT_DIR:-$PWD}"
mkdir -p -- 'logs'

run_user_job() (
    # Job control gives this subshell its own process group.
    # kill -15 0 is safe ONLY here, never in the supervisor's group.
    trap - EXIT ERR SIGUSR1
    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 143' SIGTERM
    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 130' SIGINT
    TASK_ID="${SLURM_ARRAY_TASK_ID:-1}"
    printf -v CFG_INDEX '%03d' "$TASK_ID"
    CONFIG_FILE="sweep_configs_nature_meep_verification/config_${CFG_INDEX}.json"
    mkdir -p -- .tmp logs results results_clutch_pilot results_nature_meep_verification
    OUTPUT_FILE="results_nature_meep_verification/task_${TASK_ID}_meep.json"

    ENV_PREFIX=""
    for candidate in \
        /N/u/gogordon/BigRed200/.conda/envs/meep \
        "$HOME/.conda/envs/meep" \
        "$HOME/miniconda3/envs/meep"
    do
        if [[ -x "$candidate/bin/python" ]]; then
            ENV_PREFIX="$candidate"
            break
        fi
    done

    CONDA_READY=0
    for conda_sh in \
        "$HOME/miniconda3/etc/profile.d/conda.sh" \
        /N/u/gogordon/BigRed200/miniconda3/etc/profile.d/conda.sh \
        "$HOME/anaconda3/etc/profile.d/conda.sh"
    do
        if [[ -r "$conda_sh" ]]; then
            source "$conda_sh"
            CONDA_READY=1
            break
        fi
    done

    if (( CONDA_READY == 0 )) && command -v conda >/dev/null 2>&1; then
        if CONDA_HOOK="$(conda shell.bash hook 2>/dev/null)"; then
            eval "$CONDA_HOOK"
            CONDA_READY=1
        fi
    fi

    if (( CONDA_READY == 1 )) && [[ -n "$ENV_PREFIX" ]]; then
        conda activate "$ENV_PREFIX"
    elif [[ -n "$ENV_PREFIX" ]]; then
        export CONDA_PREFIX="$ENV_PREFIX"
        export CONDA_DEFAULT_ENV=meep
    fi

    if [[ -n "$ENV_PREFIX" ]]; then
        export PATH="$ENV_PREFIX/bin:$PATH"
        export LD_LIBRARY_PATH="$ENV_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        PYTHON_BIN="$ENV_PREFIX/bin/python"
    else
        PYTHON_BIN="python3"
    fi

    module unload xalt 2>/dev/null || true
    export XALT_EXECUTABLE_TRACKING=no
    export PYTHONUNBUFFERED=1
    export OMP_NUM_THREADS=7
    export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH:-}"

    echo "Starting rotational z_eff Meep task $TASK_ID with $CONFIG_FILE on $(hostname)"
    echo "Python binary: $PYTHON_BIN"

    if command -v srun >/dev/null 2>&1 && [[ -n "${SLURM_JOB_ID:-}" ]]; then
        srun --nodes=2 -n 36 --ntasks-per-node=18 -c 7 \
            "$PYTHON_BIN" execution/run_scoped_clutch_meep.py \
            --config-file "$CONFIG_FILE" \
            --task-id "$TASK_ID" \
            --config all \
            --checkpoint-prefix chk_moments_nature_verify_task \
            --max-walltime-hours 7.5 \
            --output-file "$OUTPUT_FILE"
    else
        "$PYTHON_BIN" execution/run_scoped_clutch_meep.py \
            --config-file "$CONFIG_FILE" \
            --task-id "$TASK_ID" \
            --config all \
            --checkpoint-prefix chk_moments_nature_verify_task \
            --max-walltime-hours 7.5 \
            --output-file "$OUTPUT_FILE"
    fi
)
set -m
run_user_job &
CHILD_PID=$!
set +m
if wait "$CHILD_PID"; then
    WORKLOAD_EXIT=0
else
    WORKLOAD_EXIT=$?
fi
exit "$WORKLOAD_EXIT"
