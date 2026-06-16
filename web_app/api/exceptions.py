"""API exception types."""


class AppError(Exception):
    """Base application exception."""

    def __init__(self, message, code=None, status_code=500):
        self.message = message
        self.code = code or f"APP_{status_code}"
        self.status_code = status_code
        super().__init__(self.message)


class DatabaseConnectionError(AppError):
    """Database connection failures."""

    def __init__(self, original_error=None):
        super().__init__(
            "Database connection failed",
            code="DB_CONN_001",
            status_code=503,
        )
        self.original_error = str(original_error) if original_error else None


class InputValidationError(AppError):
    """Input validation failures."""

    def __init__(self, message, status_code=400):
        super().__init__(
            message,
            code="VAL_001",
            status_code=status_code,
        )


class SecurityError(AppError):
    """Security-related errors."""

    def __init__(self, message, status_code=403):
        super().__init__(
            message,
            code="SEC_001",
            status_code=status_code,
        )
