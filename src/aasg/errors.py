"""Application error types and stable exit codes."""

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    UNAVAILABLE = 3
    CAPTURE_FAILED = 4
    PROCESSING_FAILED = 5
    INTERRUPTED = 130


class AasgError(Exception):
    """Expected user-facing failure."""

    exit_code = ExitCode.USAGE


class ConfigurationError(AasgError):
    pass


class PrerequisiteError(AasgError):
    exit_code = ExitCode.UNAVAILABLE


class CaptureError(AasgError):
    exit_code = ExitCode.CAPTURE_FAILED


class ProcessingError(AasgError):
    exit_code = ExitCode.PROCESSING_FAILED
