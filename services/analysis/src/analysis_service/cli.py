"""Console scripts: ``issue-token`` and ``generate-keys``."""

import argparse
import math
import re
import sys
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values

from analysis_service.auth import ANALYSIS_AUDIENCE, mint
from analysis_service.settings import IssueTokenSettings

CLIENT_TOKEN_TTL = timedelta(days=30)
KEY_NAMES = ("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY")
ENV_FILE = Path(".env")


def issue_token(argv: list[str] | None = None) -> None:
    """Print a client token (``aud: "analysis-service"``)."""
    parser = argparse.ArgumentParser(
        prog="issue-token", description="Mint a client token for POST /analyses."
    )
    parser.add_argument("--sub", required=True, help="who the token is for")
    parser.add_argument(
        "--ttl",
        type=_positive_seconds,
        default=CLIENT_TOKEN_TTL.total_seconds(),
        help="lifetime in seconds (default: 30 days)",
    )
    args = parser.parse_args(argv)
    private_key = IssueTokenSettings().jwt_private_key.get_secret_value()
    print(
        mint(
            private_key,
            sub=args.sub,
            aud=ANALYSIS_AUDIENCE,
            ttl=timedelta(seconds=args.ttl),
        )
    )


def generate_keys(argv: list[str] | None = None) -> None:
    """Append a fresh dev key pair to ``./.env`` as quoted multiline values."""
    argparse.ArgumentParser(
        prog="generate-keys",
        description="Append a new JWT key pair to ./.env. "
        "Refuses if either key is already set.",
    ).parse_args(argv)
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    current = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    present = [name for name in KEY_NAMES if current.get(name)]
    if present:
        print(
            f"{ENV_FILE}: {', '.join(present)} already set; not overwriting",
            file=sys.stderr,
        )
        sys.exit(1)

    # Drop the empty placeholders (dotenv found no value, so each is one line).
    for name in KEY_NAMES:
        text = re.sub(
            rf"^[ \t]*(export[ \t]+)?{name}[ \t]*=.*(\n|$)", "", text, flags=re.M
        )
    if text and not text.endswith("\n"):
        text += "\n"
    private, public = _pem_pair()
    text += f'JWT_PRIVATE_KEY="{private}"\nJWT_PUBLIC_KEY="{public}"\n'
    # Owner-only before the private key goes in.
    ENV_FILE.touch(mode=0o600)
    ENV_FILE.chmod(0o600)
    ENV_FILE.write_text(text)
    print(f"Wrote JWT_PRIVATE_KEY and JWT_PUBLIC_KEY to {ENV_FILE}")


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if not (seconds > 0 and math.isfinite(seconds)):
        raise argparse.ArgumentTypeError(f"must be a positive number, got {value}")
    return seconds


def _pem_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private, public
