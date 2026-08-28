"""Validated question and answer decision models."""

from hashlib import sha256
from typing import List, Union

from pydantic import BaseModel, Field, StrictInt, field_validator

ChoiceValue = Union[StrictInt, List[StrictInt]]


class Question(BaseModel):
    """A multiple-choice question extracted from the current page."""

    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    options: List[str] = Field(min_length=1)
    question_type: str = "single_choice"

    @field_validator("text", "question_id")
    def strip_non_empty(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("options")
    def clean_options(cls, value: List[str]) -> List[str]:
        cleaned = [" ".join(option.split()) for option in value]
        if not cleaned or any(not value for value in cleaned):
            raise ValueError("options must contain non-empty text")
        return cleaned

    @staticmethod
    def fallback_id(text: str, options: List[str]) -> str:
        payload = "\n".join([" ".join(text.split()), *[" ".join(x.split()) for x in options]])
        return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


class AnswerDecision(BaseModel):
    """A solver's proposed zero-based index or index list."""

    choice: ChoiceValue
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    sources: List[str] = Field(default_factory=list)

    @field_validator("reason")
    def clean_reason(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("reason must not be empty")
        return value

    @field_validator("choice")
    def validate_choice_shape(cls, value: ChoiceValue) -> ChoiceValue:
        if isinstance(value, list):
            if not value:
                raise ValueError("multiple-choice decision must not be empty")
            if len(value) != len(set(value)):
                raise ValueError("choice indices must be unique")
        return value

    @property
    def choice_indices(self) -> List[int]:
        """Return a uniform list representation for browser operations."""
        return self.choice if isinstance(self.choice, list) else [self.choice]
