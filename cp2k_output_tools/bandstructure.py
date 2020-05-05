"""
Convert the CP2K band structure output to CSV files
"""

__all__ = ["SpecialPoint", "Point", "set_gen"]

import re
import argparse
from dataclasses import dataclass
from typing import List, Optional
import itertools


@dataclass
class SpecialPoint:
    number: int
    name: str
    a: float
    b: float
    c: float


@dataclass
class Point:
    a: float
    b: float
    c: float
    bands: List[float]
    spin: int
    weight: Optional[float] = None


SET_MATCH = re.compile(
    r"""
[ ]*
  SET: [ ]* (?P<setnr>\d+) [ ]*
  TOTAL [ ] POINTS: [ ]* (?P<totalpoints>\d+) [ ]*
  \n
(?P<content>
  [\s\S]*?(?=\n.*?[ ] SET|$)  # match everything until next 'SET' or EOL
)
""",
    re.VERBOSE,
)

SPOINTS_MATCH = re.compile(
    r"""
[ ]*
  POINT [ ]+ (?P<number>\d+) [ ]+ (?P<name>\S+) [ ]+ (?P<a>\S+) [ ]+ (?P<b>\S+) [ ]+ (?P<c>\S+)
""",
    re.VERBOSE,
)

POINTS_MATCH = re.compile(
    r"""
[ ]*
  Nr\. [ ]+ (?P<nr>\d+) [ ]+
  Spin [ ]+ (?P<spin>\d+) [ ]+
  K-Point [ ]+ (?P<a>\S+) [ ]+ (?P<b>\S+) [ ]+ (?P<c>\S+) [ ]*
  \n
[ ]* (?P<npoints>\d+) [ ]* \n
(?P<bands>
  [\s\S]*?(?=\n.*?[ ] Nr|$)  # match everything until next 'Nr.' or EOL
)
""",
    re.VERBOSE,
)


def _specialpoints_gen(content):
    for match in SPOINTS_MATCH.finditer(content):
        yield SpecialPoint(int(match["number"]), match["name"], float(match["a"]), float(match["b"]), float(match["c"]))


def _points_gen(content):
    for match in POINTS_MATCH.finditer(content):
        yield Point(
            a=float(match["a"]),
            b=float(match["b"]),
            c=float(match["c"]),
            bands=[float(v) for v in match["bands"].split()],
            spin=int(match["spin"]),
        )


SET_MATCH8 = re.compile(
    r"""
\#\ Set\ (?P<setnr>\d+):\ \d+\ special\ points,\ (?P<totalpoints>\d+)\ k-points,\ \d+\ bands \s*
(?P<content>
  [\s\S]*?(?=\n.*?\#\ Set|$)  # match everything until next 'SET' or EOL
)
""",
    re.VERBOSE,
)


SPOINTS_MATCH8 = re.compile(
    r"""
\#\s+ Special\ point\ (?P<number>\d+) \s+ (?P<a>\S+) \s+ (?P<b>\S+) \s+ (?P<c>\S+) \s+ (?P<name>\S+)
""",
    re.VERBOSE,
)


POINTS_MATCH8 = re.compile(
    r"""
\#\ \ Point\ (?P<nr>\d+)\s+ Spin\ (?P<spin>\d+): \s+ (?P<a>\S+) \s+ (?P<b>\S+) \s+ (?P<c>\S+) [ ]* ((?P<weight>\S+) [ ]*)? \n
\#\ \ \ Band \s+ Energy\ \[eV\] \s+ Occupation \s*
(?P<bands>
  [\s\S]*?(?=\n.*?\#\ \ Point|$)  # match everything until next '# Point' or EOL
)
""",
    re.VERBOSE,
)


def _points_gen8(content):
    for match in POINTS_MATCH8.finditer(content):
        try:
            weight = float(match["weight"])
        except TypeError:
            weight = None

        values = match["bands"].split()

        yield Point(
            a=float(match["a"]),
            b=float(match["b"]),
            c=float(match["c"]),
            bands=[float(v) for v in values[1::3]],
            weight=weight,
            spin=int(match["spin"]),
        )


def _specialpoints_gen8(content):
    for match in SPOINTS_MATCH8.finditer(content):
        yield SpecialPoint(int(match["number"]), match["name"], float(match["a"]), float(match["b"]), float(match["c"]))


def set_gen(content):
    # try with the CP2K+8+ regex first
    matchiter = SET_MATCH8.finditer(content)
    specialpoints_gen = _specialpoints_gen8
    points_gen = _points_gen8

    try:
        peek = next(matchiter)
        matchiter = itertools.chain([peek], matchiter)
    except StopIteration:
        # if nothing could be found, fallback to the older format
        matchiter = SET_MATCH.finditer(content)
        specialpoints_gen = _specialpoints_gen
        points_gen = _points_gen

    for match in matchiter:
        yield (int(match["setnr"]), int(match["totalpoints"]), specialpoints_gen(match["content"]), points_gen(match["content"]))


def cp2k_bs2csv():
    parser = argparse.ArgumentParser(
        description="""
    Convert the input from the given input file handle and write
    CSV output files based on the given pattern.
    """,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "bsfile", metavar="<bandstructure-file>", type=argparse.FileType("r"), help="the band structure file generated by CP2K"
    )
    parser.add_argument(
        "-p", "--output-pattern", help="The output pattern for the different set files", default="{bsfile.name}.set-{setnr}.csv"
    )
    args = parser.parse_args()

    content = args.bsfile.read()

    for setnr, totalpoints, specialpoints, points in set_gen(content):
        filename = args.output_pattern.format(bsfile=args.bsfile, setnr=setnr)

        with open(filename, "w") as csvout:
            print(f"writing point set {filename} (total number of k-points: {totalpoints})")
            print("with the following special points:")

            for point in specialpoints:
                print(f"  {point.name:>8}: {point.a:10.8f} / {point.b:10.8f} / {point.c:10.8f}")

            for point in points:
                csvout.write(f"{point.a:10.8f} {point.b:10.8f} {point.c:10.8f}")
                for value in point.bands:
                    csvout.write(f" {value:10.8f}")
                csvout.write("\n")