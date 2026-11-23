from dataclasses import dataclass


@dataclass
class Line:
    """One transcript line with start/end time in seconds."""
    start: float
    end: float
    text: str
