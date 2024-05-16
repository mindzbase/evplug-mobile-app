from enum import Enum


class Span(str, Enum):
    day = "day"
    week = "week"
    month = "month"
