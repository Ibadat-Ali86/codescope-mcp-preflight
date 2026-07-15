"""Malformed-source parser fixture stored as inert sample data."""


def recovered(value: int) -> int:
    """Remain extractable as a normal control symbol."""
    return value


MALFORMED_SOURCE = b"""def recovered(value: int) -> int:
    return value

def incomplete(
    value: int,
"""
