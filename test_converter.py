"""Tests for converter.py.  Run with:  python -m unittest -v test_converter"""

import os
import random
import string
import subprocess
import sys
import unittest
from decimal import Decimal

import converter as c

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "converter.py")


def run(line):
    return c.Session().handle(line)


class KnownValues(unittest.TestCase):
    CASES = [
        ("1 km to m", "1 kilometre = 1000 metre"),
        ("1 mi km", "1 mile = 1.609344 kilometre"),
        ("12 in ft", "12 inch = 1 foot"),
        ("1 lb kg", "1 pound = 0.45359237 kilogram"),
        ("100 c f", "100 Celsius = 212 Fahrenheit"),
        ("-40 f c", "-40 Fahrenheit = -40 Celsius"),
        ("0 k c", "0 Kelvin = -273.15 Celsius"),
        ("98.6 F to C", "98.6 Fahrenheit = 37 Celsius"),
        ("1 gal l", "1 gallon (US) = 3.785411784 litre"),
        ("1 GiB MB", "1 gibibyte = 1073.741824 megabyte"),
        ("8 bit byte", "8 bit = 1 byte"),
        ("36 km/h m/s", "36 kilometre per hour = 10 metre per second"),
        ("1 day h", "1 day = 24 hour"),
        ("1 ha m²", "1 hectare = 10000 square metre"),
        ("5km mi", "5 kilometre = 3.10685596119 mile"),
        ("1,000 m km", "1000 metre = 1 kilometre"),
        ("1e3 g kg", "1000 gram = 1 kilogram"),
        ("0 m ft", "0 metre = 0 foot"),
        ("-0 m ft", "0 metre = 0 foot"),
        ("１２ ｉｎ ｆｔ", "12 inch = 1 foot"),  # full-width characters
        ("3 FEET -> Inches", "3 foot = 36 inch"),
    ]

    def test_known_values(self):
        for line, expected in self.CASES:
            with self.subTest(line=line):
                self.assertEqual(run(line), expected)

    def test_round_trip(self):
        for category, units in c.LINEAR_UNITS.items():
            keys = list(units)
            for a in keys:
                for b in keys:
                    v = Decimal("123.456")
                    there = c.convert(v, (category, a), (category, b))
                    back = c.convert(there, (category, b), (category, a))
                    self.assertAlmostEqual(float(back), float(v), places=9)


class BadInput(unittest.TestCase):
    ATTACKS = [
        "", "   ", "abc", "5", "5 km", "km mi 5", "5 km to", "five km mi",
        "5 km kg", "5 c m", "nan km mi", "inf km mi", "-inf c f", "Infinity m ft",
        "1e999999999 km mi", "1e-999999999 km mi", "9" * 5000 + " km mi",
        "1e300 mi mm", "-1 km mi", "-500 c f", "-1 k c", "0x10 m ft",
        "1_000 m km", "1,2 m km", "1..2 m ft", "--5 m ft", "5 m m m m",
        "٥ km mi", "5 km mi; rm -rf /", "%s%s%s km mi", "{0} km mi",
        "\x00\x01\x02", "\t\n\r", "5\x00 km mi", "🚀 km mi", "5 🚀 mi",
        "list nothing", "list " + "x" * 300, "' OR 1=1 --", "None", "True km mi",
        "5 km to to to mi", "‮5 km mi", "5 " + "k" * 190 + " mi",
    ]

    def test_attacks_never_raise(self):
        for line in self.ATTACKS:
            with self.subTest(line=line[:30]):
                reply = run(line)
                self.assertIsInstance(reply, str)

    def test_errors_are_explained(self):
        for line in ["abc", "5 km kg", "-1 km mi", "-500 c f", "nan km mi", "1e999999999 km mi"]:
            with self.subTest(line=line):
                self.assertTrue(run(line).startswith("Error:"))

    def test_non_string_input(self):
        for value in [None, 5, b"5 km mi", ["5", "km"]]:
            self.assertTrue(c.Session().handle(value).startswith("Error:"))

    def test_random_fuzz(self):
        rng = random.Random(1234)
        alphabet = string.printable + "°²³µ€漢字🙂​‮"
        units = list(c.ALIASES)
        for _ in range(20000):
            kind = rng.random()
            if kind < 0.4:
                line = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))
            else:
                number = rng.choice([
                    str(rng.uniform(-1e6, 1e6)), str(rng.randint(-10**9, 10**9)),
                    "%de%d" % (rng.randint(1, 9), rng.randint(-400, 400)), "", ".", "-",
                ])
                line = "%s %s %s" % (number, rng.choice(units), rng.choice(units))
            reply = run(line)
            self.assertIsInstance(reply, str)


class Structure(unittest.TestCase):
    def test_aliases_unique_and_complete(self):
        for category, units in c.LINEAR_UNITS.items():
            for key in units:
                self.assertEqual(c.ALIASES[c._normalize_unit(key)], (category, key))

    def test_commands(self):
        s = c.Session()
        self.assertIn("How to use", s.handle("help"))
        self.assertIn("LENGTH", s.handle("list length"))
        self.assertEqual(s.handle("history"), "No conversions yet.")
        s.handle("1 km m")
        self.assertIn("kilometre", s.handle("history"))
        self.assertEqual(s.handle("quit"), "Goodbye!")
        self.assertTrue(s.finished)

    def test_history_is_bounded(self):
        s = c.Session()
        for i in range(100):
            s.handle("%d m ft" % i)
        self.assertEqual(len(s.history), c.HISTORY_SIZE)


class CommandLine(unittest.TestCase):
    def call(self, args, stdin=b""):
        return subprocess.run(
            [sys.executable, SCRIPT] + args, input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )

    def test_one_shot(self):
        out = self.call(["10", "km", "to", "mi"])
        self.assertEqual(out.returncode, 0)
        self.assertIn(b"6.21371192237", out.stdout)

    def test_one_shot_error_exit_code(self):
        out = self.call(["banana"])
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stderr, b"")

    def test_interactive_garbage_then_eof(self):
        junk = b"\n".join([b"hello", b"\xff\xfe\xfa", b"5 km mi", b"x" * 100000, b"1e99999 m ft"])
        out = self.call([], stdin=junk)  # ends without 'quit' -> EOF
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr, b"")
        self.assertIn(b"3.10685596119", out.stdout)

    def test_flags(self):
        self.assertEqual(self.call(["--help"]).returncode, 0)
        self.assertEqual(self.call(["--list"]).returncode, 0)
        self.assertEqual(self.call(["--list", "nope"]).returncode, 1)


if __name__ == "__main__":
    unittest.main()
