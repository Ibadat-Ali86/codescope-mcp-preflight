"""Service parser fixture."""

from sample_support import BaseService, ServiceMeta, registered


@registered("user")
class UserService(BaseService, metaclass=ServiceMeta):
    """Coordinate user operations."""

    @property
    def display_name(self) -> str:
        """Return the display label."""
        return "User"

    @classmethod
    async def load(cls, user_id: int) -> "UserService":
        """Load one service instance."""
        return cls()


def outer() -> str:
    """Return a value without exposing the nested helper as a symbol."""

    def nested() -> str:
        return "hidden"

    return nested()
