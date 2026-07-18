"""Reusable, code-owned operational workflow engine.

The workflow package deliberately keeps templates in code for the hackathon
submission.  It provides a small evidence-to-decision layer without turning
Company Brain into a generic no-code workflow product.
"""

from backend.workflows.service import WorkflowService

__all__ = ["WorkflowService"]
