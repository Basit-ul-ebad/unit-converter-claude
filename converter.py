#!/usr/bin/env python3
"""
Unit Converter (hardened edition)
=================================

A command-line unit converter built to keep running no matter what the
user types. Standard library only, works on Python 3.7+.

Usage
-----
    python converter.py                 # interactive mode
    python converter.py 5 km to mi      # one-shot conversion
    python converter.py --list          # show every supported unit
    python converter.py --help

Inside interactive mode you can type things like:
    5 km to mi
    98.6 F C
    2.5GB MiB
    help | list | list length | history | quit
"""

import sys

if sys.version_info < (3, 7):  # plain syntax so old Pythons can print this
    sys.stderr.write("This program needs Python 3.7 or newer.\n")
    sys.exit(1)

import re
import unicodedata
from collections import deque
from decimal import Decimal, DecimalException, localcontext

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Limits: every input is bounded so nothing can exhaust time or memory.
# ---------------------------------------------------------------------------
MAX_LINE_LENGTH = 200          # characters accepted per command
MAX_NUMBER_LENGTH = 60         # characters accepted for the number itself
MAX_EXPONENT = 300             # magnitudes allowed: 1e-300 .. 1e300
PRECISION = 50                 # digits used while calculating
DISPLAY_DIGITS = 12            # significant digits shown to the user
HISTORY_SIZE = 10


class ConversionError(ValueError):
    """A problem caused by the user's input. The message is safe to print."""


# ---------------------------------------------------------------------------
# Unit tables. Each unit: key -> (factor to base unit, display name, aliases)
# Factors are strings so they stay exact. "a/b" means a divided by b.
# ---------------------------------------------------------------------------
LINEAR_UNITS = {
    "length": {
        "mm": ("0.001", "millimetre", ["millimeter", "millimeters", "millimetres"]),
        "cm": ("0.01", "centimetre", ["centimeter", "centimeters", "centimetres"]),
        "m": ("1", "metre", ["meter", "meters", "metres"]),
        "km": ("1000", "kilometre", ["kilometer", "kilometers", "kilometres", "kms"]),
        "in": ("0.0254", "inch", ["inch", "inches", '"']),
        "ft": ("0.3048", "foot", ["foot", "feet", "'"]),
        "yd": ("0.9144", "yard", ["yard", "yards", "yds"]),
        "mi": ("1609.344", "mile", ["mile", "miles"]),
        "nmi": ("1852", "nautical mile", ["nauticalmile", "nauticalmiles"]),
    },
    "mass": {
        "mg": ("0.000001", "milligram", ["milligram", "milligrams"]),
        "g": ("0.001", "gram", ["gram", "grams", "gm"]),
        "kg": ("1", "kilogram", ["kilogram", "kilograms", "kgs", "kilo", "kilos"]),
        "t": ("1000", "tonne", ["tonne", "tonnes", "ton", "tons"]),
        "oz": ("0.028349523125", "ounce", ["ounce", "ounces"]),
        "lb": ("0.45359237", "pound", ["pound", "pounds", "lbs"]),
        "st": ("6.35029318", "stone", ["stone", "stones"]),
    },
    "volume": {
        "ml": ("0.001", "millilitre", ["milliliter", "milliliters", "millilitres"]),
        "l": ("1", "litre", ["liter", "liters", "litres", "litre"]),
        "m3": ("1000", "cubic metre", ["cubicmetre", "cubicmeter"]),
        "tsp": ("0.00492892159375", "teaspoon (US)", ["teaspoon", "teaspoons"]),
        "tbsp": ("0.01478676478125", "tablespoon (US)", ["tablespoon", "tablespoons"]),
        "floz": ("0.0295735295625", "fluid ounce (US)", ["fluidounce", "fluidounces"]),
        "cup": ("0.2365882365", "cup (US)", ["cups"]),
        "pt": ("0.473176473", "pint (US)", ["pint", "pints"]),
        "qt": ("0.946352946", "quart (US)", ["quart", "quarts"]),
        "gal": ("3.785411784", "gallon (US)", ["gallon", "gallons"]),
        "impgal": ("4.54609", "gallon (imperial)", ["ukgal", "imperialgallon"]),
    },
    "area": {
        "mm2": ("0.000001", "square millimetre", ["sqmm"]),
        "cm2": ("0.0001", "square centimetre", ["sqcm"]),
        "m2": ("1", "square metre", ["sqm"]),
        "ha": ("10000", "hectare", ["hectare", "hectares"]),
        "km2": ("1000000", "square kilometre", ["sqkm"]),
        "in2": ("0.00064516", "square inch", ["sqin"]),
        "ft2": ("0.09290304", "square foot", ["sqft"]),
        "yd2": ("0.83612736", "square yard", ["sqyd"]),
        "acre": ("4046.8564224", "acre", ["acres", "ac"]),
        "mi2": ("2589988.110336", "square mile", ["sqmi"]),
    },
    "speed": {
        "m/s": ("1", "metre per second", ["mps"]),
        "km/h": ("1000/3600", "kilometre per hour", ["kmh", "kph", "kmph"]),
        "mph": ("0.44704", "mile per hour", ["mi/h"]),
        "kn": ("1852/3600", "knot", ["knot", "knots", "kt"]),
        "ft/s": ("0.3048", "foot per second", ["fps"]),
    },
    "time": {
        "ms": ("0.001", "millisecond", ["millisecond", "milliseconds"]),
        "s": ("1", "second", ["sec", "secs", "second", "seconds"]),
        "min": ("60", "minute", ["mins", "minute", "minutes"]),
        "h": ("3600", "hour", ["hr", "hrs", "hour", "hours"]),
        "day": ("86400", "day", ["days", "d"]),
        "week": ("604800", "week", ["weeks", "wk"]),
        "year": ("31557600", "year (365.25 days)", ["years", "yr", "yrs"]),
    },
    "data": {
        "bit": ("0.125", "bit", ["bits"]),
        "byte": ("1", "byte", ["bytes", "b"]),
        "kb": ("1000", "kilobyte", ["kilobyte", "kilobytes"]),
        "mb": ("1000000", "megabyte", ["megabyte", "megabytes"]),
        "gb": ("1000000000", "gigabyte", ["gigabyte", "gigabytes"]),
        "tb": ("1000000000000", "terabyte", ["terabyte", "terabytes"]),
        "kib": ("1024", "kibibyte", ["kibibyte"]),
        "mib": ("1048576", "mebibyte", ["mebibyte"]),
        "gib": ("1073741824", "gibibyte", ["gibibyte"]),
        "tib": ("1099511627776", "tebibyte", ["tebibyte"]),
    },
}

TEMPERATURE_UNITS = {
    "c": ("Celsius", ["celsius", "centigrade", "degc"]),
    "f": ("Fahrenheit", ["fahrenheit", "degf"]),
    "k": ("Kelvin", ["kelvin", "kelvins"]),
    "r": ("Rankine", ["rankine"]),
}

CATEGORIES = list(LINEAR_UNITS) + ["temperature"]


def _normalize_unit(text):
    """Lower-case, fold look-alike characters (² -> 2), drop spaces and '°'."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("°", "").replace("º", "")
    text = re.sub(r"\s+", "", text)
    return text.casefold()


def _to_decimal_factor(text):
    if "/" in text:
        top, bottom = text.split("/")
        return Decimal(top) / Decimal(bottom)
    return Decimal(text)


def _build_alias_table():
    """Map every accepted spelling to (category, unit key).

    Raises at start-up if two units share a spelling, so an ambiguous table
    can never ship silently.
    """
    table = {}

    def add(alias, target):
        alias = _normalize_unit(alias)
        if alias in table and table[alias] != target:
            raise RuntimeError("Duplicate unit alias %r" % alias)
        table[alias] = target

    for category, units in LINEAR_UNITS.items():
        for key, (_factor, _name, aliases) in units.items():
            add(key, (category, key))
            for alias in aliases:
                add(alias, (category, key))
    for key, (_name, aliases) in TEMPERATURE_UNITS.items():
        add(key, ("temperature", key))
        for alias in aliases:
            add(alias, ("temperature", key))
    return table


with localcontext() as _ctx:
    _ctx.prec = PRECISION
    FACTORS = {
        (category, key): _to_decimal_factor(spec[0])
        for category, units in LINEAR_UNITS.items()
        for key, spec in units.items()
    }
ALIASES = _build_alias_table()


def unit_name(category, key):
    if category == "temperature":
        return TEMPERATURE_UNITS[key][0]
    return LINEAR_UNITS[category][key][1]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
_NUMBER_RE = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z", re.ASCII
)
_THOUSANDS_RE = re.compile(r"[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]*)?\Z", re.ASCII)
_LEADING_NUMBER_RE = re.compile(
    r"([+-]?(?:[0-9][0-9,]*(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)(.+)\Z",
    re.ASCII,
)
_CONNECTORS = {"to", "in", "into", "as", "->", "=>", "=", ">"}


def parse_number(text):
    """Turn user text into a finite Decimal or raise ConversionError."""
    text = unicodedata.normalize("NFKC", text).strip().replace("_", "")
    if not text:
        raise ConversionError("Please enter a number.")
    if len(text) > MAX_NUMBER_LENGTH:
        raise ConversionError("That number is too long (max %d characters)." % MAX_NUMBER_LENGTH)
    if "," in text:
        if not _THOUSANDS_RE.match(text):
            raise ConversionError(
                "'%s' is not a valid number. Use a dot for decimals, e.g. 2.5" % text
            )
        text = text.replace(",", "")
    if not _NUMBER_RE.match(text):
        raise ConversionError("'%s' is not a valid number." % text)
    try:
        value = Decimal(text)
    except DecimalException:
        raise ConversionError("'%s' is not a valid number." % text)
    if value and not -MAX_EXPONENT <= value.adjusted() <= MAX_EXPONENT:
        raise ConversionError(
            "Number out of range. Use values between 1e-%d and 1e%d." % (MAX_EXPONENT, MAX_EXPONENT)
        )
    return value + 0 if value else Decimal(0)  # turns -0 into 0


def parse_unit(text):
    key = ALIASES.get(_normalize_unit(text))
    if key is None:
        shown = text if len(text) <= 20 else text[:20] + "..."
        raise ConversionError("Unknown unit '%s'. Type 'list' to see all units." % shown)
    return key


def parse_query(line):
    """Split '5 km to mi' / '5km mi' into (Decimal, from_key, to_key)."""
    tokens = unicodedata.normalize("NFKC", line).split()
    first = tokens[0].replace("_", "") if tokens else ""
    if first and not (_NUMBER_RE.match(first) or _THOUSANDS_RE.match(first)):
        match = _LEADING_NUMBER_RE.match(tokens[0])
        if match:  # '5km' -> '5', 'km'
            tokens = [match.group(1), match.group(2)] + tokens[1:]
    # Drop a connector word only where one belongs ('in' is also the inch unit).
    if len(tokens) == 4 and tokens[2].casefold() in _CONNECTORS:
        del tokens[2]
    if len(tokens) != 3:
        raise ConversionError(
            "I didn't understand that. Try something like:  5 km to mi   (type 'help' for more)"
        )
    return parse_number(tokens[0]), parse_unit(tokens[1]), parse_unit(tokens[2])


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------
_ABSOLUTE_ZERO = {"c": Decimal("-273.15"), "f": Decimal("-459.67"), "k": Decimal(0), "r": Decimal(0)}


def _temp_to_kelvin(value, unit):
    if unit == "c":
        return value + Decimal("273.15")
    if unit == "f":
        return (value + Decimal("459.67")) * 5 / 9
    if unit == "r":
        return value * 5 / 9
    return value


def _temp_from_kelvin(value, unit):
    if unit == "c":
        return value - Decimal("273.15")
    if unit == "f":
        return value * 9 / 5 - Decimal("459.67")
    if unit == "r":
        return value * 9 / 5
    return value


def convert(value, source, target):
    """Convert value between two (category, key) units. Returns a Decimal."""
    src_cat, src_key = source
    dst_cat, dst_key = target
    if src_cat != dst_cat:
        raise ConversionError(
            "Can't convert %s (%s) to %s (%s)."
            % (unit_name(src_cat, src_key), src_cat, unit_name(dst_cat, dst_key), dst_cat)
        )
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ConversionError("The value must be a finite number.")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        try:
            if src_cat == "temperature":
                if value < _ABSOLUTE_ZERO[src_key]:
                    raise ConversionError(
                        "%s %s is below absolute zero (%s %s)."
                        % (format_number(value), unit_name(src_cat, src_key),
                           _ABSOLUTE_ZERO[src_key], unit_name(src_cat, src_key))
                    )
                result = _temp_from_kelvin(_temp_to_kelvin(value, src_key), dst_key)
            else:
                if value < 0:
                    raise ConversionError("A %s can't be negative." % src_cat)
                result = value * FACTORS[source] / FACTORS[target]
        except DecimalException:
            raise ConversionError("That value can't be converted (out of range).")
    if not result.is_finite():
        raise ConversionError("That value can't be converted (out of range).")
    return result


def format_number(value):
    """Readable output: 12 significant digits, no '-0', no trailing zeros."""
    with localcontext() as ctx:
        ctx.prec = DISPLAY_DIGITS
        value = +value  # rounds to DISPLAY_DIGITS
    if value.is_zero():
        return "0"
    if -7 <= value.adjusted() < 16:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
    else:
        text = format(value.normalize(), "E").replace("E+", "e").replace("E", "e")
    return text


# ---------------------------------------------------------------------------
# Text user interface
# ---------------------------------------------------------------------------
HELP_TEXT = """\
How to use:
  <number> <from-unit> to <to-unit>      e.g.  5 km to mi
  The word 'to' is optional:             e.g.  98.6 f c
  Number and unit can touch:             e.g.  2.5GB MiB

Commands:
  list              show all units
  list <category>   show one category ({cats})
  history           show your last {hist} conversions
  help              show this message
  quit / exit       leave (Ctrl+C or Ctrl+D also work)
""".format(cats=", ".join(CATEGORIES), hist=HISTORY_SIZE)


def list_units(category=None):
    if category is not None:
        category = category.casefold()
        if category not in CATEGORIES:
            raise ConversionError(
                "Unknown category. Choose one of: %s" % ", ".join(CATEGORIES)
            )
    lines = []
    for cat in CATEGORIES:
        if category and cat != category:
            continue
        lines.append(cat.upper())
        keys = TEMPERATURE_UNITS if cat == "temperature" else LINEAR_UNITS[cat]
        for key in keys:
            lines.append("  %-8s %s" % (key, unit_name(cat, key)))
    return "\n".join(lines)


class Session:
    """Holds history and turns one input line into one reply string."""

    def __init__(self):
        self.history = deque(maxlen=HISTORY_SIZE)
        self.finished = False

    def handle(self, line):
        """Never raises (except for interrupts); always returns text."""
        try:
            return self._handle(line)
        except ConversionError as exc:
            return "Error: %s" % exc
        except (KeyboardInterrupt, SystemExit):
            raise
        except MemoryError:
            return "Error: not enough memory for that request."
        except Exception:  # last line of defence: report, keep running
            return "Error: something unexpected went wrong with that input. Please try again."

    def _handle(self, line):
        if not isinstance(line, str):
            raise ConversionError("Input must be text.")
        if len(line) > MAX_LINE_LENGTH:
            raise ConversionError("Input is too long (max %d characters)." % MAX_LINE_LENGTH)
        line = "".join(ch for ch in line if ch.isprintable()).strip()
        if not line:
            return ""
        words = line.split()
        command = words[0].casefold()
        if command in ("quit", "exit", "q", "bye"):
            self.finished = True
            return "Goodbye!"
        if command in ("help", "h", "?"):
            return HELP_TEXT
        if command == "list":
            return list_units(words[1] if len(words) > 1 else None)
        if command == "history":
            return "\n".join(self.history) if self.history else "No conversions yet."

        value, source, target = parse_query(line)
        result = convert(value, source, target)
        reply = "%s %s = %s %s" % (
            format_number(value), unit_name(*source),
            format_number(result), unit_name(*target),
        )
        self.history.append(reply)
        return reply


def _safe_print(text=""):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc, "replace"), flush=True)


def _prepare_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    try:
        sys.stdin.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def interactive():
    session = Session()
    _safe_print("Unit Converter %s  -  type 'help' for instructions, 'quit' to leave." % __version__)
    while not session.finished:
        try:
            line = input("> ")
        except EOFError:
            _safe_print()
            break
        reply = session.handle(line)
        if reply:
            _safe_print(reply)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    _prepare_streams()
    try:
        if not argv:
            return interactive()
        first = argv[0].casefold()
        if first in ("-h", "--help"):
            _safe_print(__doc__.strip())
            return 0
        if first in ("-v", "--version"):
            _safe_print(__version__)
            return 0
        if first in ("-l", "--list"):
            session = Session()
            reply = session.handle("list " + " ".join(argv[1:]))
            _safe_print(reply)
            return 1 if reply.startswith("Error:") else 0
        session = Session()
        reply = session.handle(" ".join(argv))
        _safe_print(reply)
        return 1 if reply.startswith("Error:") else 0
    except KeyboardInterrupt:
        try:
            _safe_print("\nGoodbye!")
        except Exception:
            pass
        return 130
    except BrokenPipeError:
        # Output was piped into something that closed early (e.g. `| head`).
        try:
            import os
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except Exception:
            pass
        return 0
    except Exception:
        try:
            sys.stderr.write("Unexpected error. Please report how you got here.\n")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
