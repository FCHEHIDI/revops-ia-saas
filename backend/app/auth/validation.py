import re

PASSWORD_MIN_LENGTH = 12
PASSWORD_RULES = [
    ("lowercase", re.compile(r"[a-z]")),
    ("uppercase", re.compile(r"[A-Z]")),
    ("digit", re.compile(r"\d")),
    ("special character", re.compile(r"[^A-Za-z0-9]")),
]
MFA_CODE_PATTERN = re.compile(r"^\d{6}$")


def validate_password_format(password: str) -> None:
    """Validate password complexity according to policy.

    Args:
        password: The plaintext password to validate.

    Raises:
        ValueError: If the password does not meet the complexity requirements.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            "Password must be at least 12 characters long and include uppercase, lowercase, digits, and special characters."
        )
    if re.search(r"\s", password):
        raise ValueError("Password must not contain whitespace.")
    missing = [name for name, pattern in PASSWORD_RULES if not pattern.search(password)]
    if missing:
        raise ValueError(
            "Password must include: " + ", ".join(missing) + "."
        )


def validate_mfa_code(code: str | None) -> str | None:
    """Validate that the MFA code is a 6-digit TOTP string.

    Args:
        code: The MFA code to validate.

    Returns:
        The validated MFA code, or None when the value is omitted or empty.

    Raises:
        ValueError: If the code is present and not exactly 6 digits.
    """
    if code is None or code == "":
        return None
    if not MFA_CODE_PATTERN.fullmatch(code):
        raise ValueError("MFA code must be exactly 6 digits.")
    return code
