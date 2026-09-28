"""Keep startup and duplicate state records out of Home Assistant events."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "echo_button"))

from protocol import ButtonTransitionTracker


class ButtonTransitionTests(unittest.TestCase):
    def test_unmatched_release_and_repeated_states(self) -> None:
        tracker = ButtonTransitionTracker()
        observed = [
            tracker.observe(state)
            for state in ("released", "pressed", "pressed", "released", "released")
        ]
        self.assertEqual(observed, [None, "pressed", None, "released", None])

    def test_reconnection_resets_pressed_state(self) -> None:
        previous = ButtonTransitionTracker()
        self.assertEqual(previous.observe("pressed"), "pressed")
        reconnected = ButtonTransitionTracker()
        self.assertIsNone(reconnected.observe("released"))
        self.assertEqual(reconnected.observe("pressed"), "pressed")

    def test_later_press_recovers_after_missing_release(self) -> None:
        tracker = ButtonTransitionTracker()
        self.assertEqual(tracker.observe("pressed", now=10.0), "pressed")
        self.assertIsNone(tracker.observe("pressed", now=10.1))
        self.assertIsNone(tracker.observe("pressed", now=11.9))
        self.assertEqual(tracker.observe("pressed", now=14.0), "pressed")
        self.assertEqual(tracker.observe("released", now=14.2), "released")
        self.assertIsNone(tracker.observe("released", now=14.3))


if __name__ == "__main__":
    unittest.main()
