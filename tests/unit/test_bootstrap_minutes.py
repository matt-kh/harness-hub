"""bootstrap's last line: the declared minutes of the manual steps still to do (principle 2's
time-to-first-useful-session proxy)."""
from __future__ import annotations

import unittest

import helpers  # noqa: F401  (puts lib/ on sys.path)

from harness import bootstrap as B


class RemainingLineTest(unittest.TestCase):
    def test_sums_minutes(self):
        rows = [{"minutes": 2}, {"minutes": None}, {"minutes": 3}]
        self.assertEqual(B.remaining_line(rows), "≈ 5 minutes of manual steps remain (harness steps --pending)")

    def test_singular_and_none(self):
        self.assertEqual(B.remaining_line([{"minutes": 1}]),
                         "≈ 1 minute of manual steps remain (harness steps --pending)")
        self.assertTrue(B.remaining_line([]).startswith("≈ 0 minutes"))


if __name__ == "__main__":
    unittest.main()
