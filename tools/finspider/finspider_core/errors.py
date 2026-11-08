"""Exceptions with messages meant to be shown to the user as-is."""


class FinspiderError(Exception):
    """Base class. The CLI prints the message and exits non-zero."""

    exit_code = 1


class ConfigError(FinspiderError):
    exit_code = 2


class TickerNotFound(FinspiderError):
    exit_code = 3


class DataUnavailable(FinspiderError):
    exit_code = 4


class UserAborted(FinspiderError):
    exit_code = 130
