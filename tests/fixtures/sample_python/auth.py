"""Authentication parser fixture."""


async def authenticate(token: str) -> bool:
    """Validate an authentication token asynchronously."""
    return bool(token)


class AuthService:
    """Provide authentication operations."""

    def __init__(self, issuer: str) -> None:
        """Store the expected issuer."""
        self.issuer = issuer

    async def validate_token(self, token: str) -> bool:
        """Validate a token against the configured issuer."""
        return bool(token and self.issuer)
