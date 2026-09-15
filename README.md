# Unit Converter — hardened (Claude-written) version

A command-line unit converter written by Claude (an AI model by Anthropic) to be
as hard to crash as possible. Its sister repository,
[unit-converter-human](https://github.com/Basit-ul-ebad/unit-converter-human), does the same job in the simple style of a
beginner programmer. The two exist to compare the approaches.

## Run it

Requires Python 3.7 or newer. No packages to install.

```bash
python converter.py                 # interactive mode
python converter.py 5 km to mi      # one-shot conversion
python converter.py --list          # every supported unit
```

Example session:

```
> 5 km to mi
5 kilometre = 3.10685596119 mile
> 98.6 F C
98.6 Fahrenheit = 37 Celsius
> 2.5GB MiB
2.5 gigabyte = 2384.18579102 mebibyte
> banana
Error: I didn't understand that. Try something like:  5 km to mi   (type 'help' for more)
```

## Supported units (63)

| Category | Units |
|---|---|
| Length | mm, cm, m, km, in, ft, yd, mi, nmi |
| Mass | mg, g, kg, t, oz, lb, st |
| Volume | ml, l, m3, tsp, tbsp, floz, cup, pt, qt, gal, impgal |
| Area | mm2, cm2, m2, ha, km2, in2, ft2, yd2, acre, mi2 |
| Speed | m/s, km/h, mph, kn, ft/s |
| Time | ms, s, min, h, day, week, year |
| Data | bit, byte, kb, mb, gb, tb, kib, mib, gib, tib |
| Temperature | c, f, k, r |

Full names and plurals work too (`kilometers`, `feet`, `pounds`, `celsius`).
Unit names are not case-sensitive.

## How it resists crashing

| Attack | What happens |
|---|---|
| Letters instead of numbers (`abc km mi`) | Clear error, program keeps running |
| `nan`, `inf`, `0x10`, `1..2`, `--5` | Rejected by a strict number pattern |
| Huge / tiny numbers (`1e999999999`) | Rejected: allowed range is 1e-300 to 1e300 |
| Very long input (100,000 characters) | Rejected: 200-character limit |
| Different categories (`5 km kg`) | "Can't convert kilometre (length) to kilogram (mass)" |
| Below absolute zero (`-500 C F`) | Rejected with the real limit |
| Negative mass, length, etc. | Rejected with an explanation |
| Unicode tricks: full-width digits, `²`, emoji, control characters, invalid bytes | Normalized or rejected safely |
| Ctrl+C / Ctrl+D / closed input stream | Clean "Goodbye!" exit |
| Output piped into a program that closes early | Handled without a traceback |
| Anything unforeseen | Caught by a last-resort handler; the session continues |

Maths uses Python's `Decimal` with 50 digits of precision, so
`0.1 + 0.2`-style floating-point errors don't appear, and results are shown
to 12 significant digits.

## Tests

```bash
python -m unittest -v test_converter
```

The suite checks known conversions, round trips between every pair of units,
40+ hand-written attack strings, 20,000 random fuzz inputs, and the program run
as a real process with garbage bytes on standard input.

## Honest limits

"Uncrashable" means no input typed into the program can make it crash. Nothing can stop
someone from closing the terminal, killing the process, or running it on a
machine with no memory left.
