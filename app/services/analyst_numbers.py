"""Presentation precision for analyst prose; structured facts keep their precision."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re


# Leave references, links, code, version numbers and scientific notation intact.
# A trailing unit (e.g. 6.2345s or 120.567°) is still readable measurement prose.
_TOKENS = re.compile(
    r"https?://[^\s<>]+|`[^`]*`|\[event-[^\]\s]+\]"
    r"|\b[A-Za-z]\w*[-_][\w.-]+"
    r"|\b\d+(?:\.\d+){2,}\b"
    r"|\b\d+(?:\.\d+)?[eE][+-]?\d+\b"
    r"|(?<![\dA-Za-z_.])(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{3,})(?![\d.])"
)


def format_analyst_numbers(text: str) -> str:
    def rounded(match: re.Match) -> str:
        number = match.group('number')
        if number is None:
            return match.group()
        value = Decimal(number.replace(',', ''))
        with localcontext() as context:
            context.prec = max(28, len(value.as_tuple().digits) + 4)
            value = value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if not value:
            return '0'
        formatted = format(value, ',f' if ',' in number else 'f').rstrip('0').rstrip('.')
        return ('+' if number.startswith('+') else '') + formatted
    return _TOKENS.sub(rounded, text)
