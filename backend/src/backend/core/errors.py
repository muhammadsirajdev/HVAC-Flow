"""Shared exception types."""


class SlotTaken(Exception):
    """The chosen slot was booked by someone else in the meantime."""


class AlreadyBooked(Exception):
    """The customer already has an open, booked case."""

    def __init__(self, case_id: int):
        super().__init__(f"customer already has booked case {case_id}")
        self.case_id = case_id


class InvalidTransition(Exception):
    """A case status change that the lifecycle does not allow."""


class MCPError(Exception):
    """An MCP server call failed or returned an error result."""


class LateChange(Exception):
    """A change too close to the visit: a person must handle it."""


class ContactInUse(Exception):
    """The new email/phone already belongs to another customer."""
