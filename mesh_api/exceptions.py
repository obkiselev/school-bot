"""Custom exceptions for МЭШ API errors."""


class MeshAPIError(Exception):
    """Base exception for МЭШ API errors."""
    pass


class AuthenticationError(MeshAPIError):
    """Invalid credentials or expired token."""
    pass


class RateLimitError(MeshAPIError):
    """API rate limit exceeded."""
    pass


class NetworkError(MeshAPIError):
    """Network connectivity issues."""
    pass


class DataNotFoundError(MeshAPIError):
    """Requested data not found in МЭШ."""
    pass


class InvalidResponseError(MeshAPIError):
    """API returned unexpected response format."""
    pass
