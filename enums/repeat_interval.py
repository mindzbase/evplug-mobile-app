from enum import Enum


class RepeatInterval(str, Enum):
    weekdays = "Weekdays"
    weekends = "Weekends"
    onetime = "One-time"
    custom = "Custom"
