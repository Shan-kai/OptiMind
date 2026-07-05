"""Verification result models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    """Outcome of a single check."""

    check_name: str = Field(description="Name of the verification check")
    passed: bool
    message: str = ""
    details: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    """Aggregated report from all verification checks."""

    results: list[VerificationResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when every check passed."""
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[VerificationResult]:
        """Checks that failed."""
        return [r for r in self.results if not r.passed]

    def add(self, result: VerificationResult) -> None:
        """Append a check result."""
        self.results.append(result)
