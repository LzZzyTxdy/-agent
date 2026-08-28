"""Application-specific exception hierarchy."""


class QuizAgentError(Exception):
    """Base class for expected agent failures."""


class ConfigurationError(QuizAgentError):
    """Raised when required configuration is missing or invalid."""


class ExtractionError(QuizAgentError):
    """Raised when a valid question cannot be extracted from the DOM."""


class BrowserStateError(QuizAgentError):
    """Raised when the browser is closed or the page cannot progress."""


class SolverError(QuizAgentError):
    """Raised after bounded solver retries are exhausted."""


class DecisionRejected(QuizAgentError):
    """Raised when policy rejects or stops a decision."""
