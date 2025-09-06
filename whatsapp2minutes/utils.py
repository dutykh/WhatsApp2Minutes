"""
Author: Dr. Denys Dutykh (Khalifa University of Science and Technology, Abu Dhabi, UAE)
"""

import re


def compact_committee_name(name: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", name)
    compact = "".join(tokens) if tokens else "Committee"
    return compact


def default_meeting_prefix_from_name(name: str) -> str:
    return f"{compact_committee_name(name)}Meeting"
