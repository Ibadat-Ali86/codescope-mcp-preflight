"""Validation parser fixture."""

from typing_extensions import deprecated


def validate_email(email: str) -> bool:
    """Return whether an email has a simple local and domain shape."""
    local, separator, domain = email.partition("@")
    return bool(local and separator and "." in domain)


@deprecated("Use validate_email.")
def validate_username(
    username: str,
    *,
    minimum_length: int = 3,
) -> bool:
    """Validate a username length."""
    return len(username) >= minimum_length
