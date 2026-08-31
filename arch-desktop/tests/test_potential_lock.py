from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "hypr" / "potential-lock"
LOADER = importlib.machinery.SourceFileLoader("potential_lock", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = MODULE
LOADER.exec_module(MODULE)


class PotentialLockTest(unittest.TestCase):
    def policy(self, pin: str = "8642", **overrides: float | int):
        values: dict[str, float | int] = {
            "invalid_key_limit": 3,
            "corner_contacts": 3,
            "corner_radius": 20,
            "motion_commit": 80,
            "reverse_distance": 60,
        }
        values.update(overrides)
        return MODULE.Policy.create(pin, **values)

    def test_pin_is_verified_by_prefix_without_serializing_plaintext(self) -> None:
        policy = self.policy()
        state = MODULE.InputState(policy)

        self.assertEqual(state.key_pressed("8"), MODULE.Decision.WAIT)
        self.assertEqual(state.key_pressed("6"), MODULE.Decision.WAIT)
        self.assertEqual(state.key_pressed("4"), MODULE.Decision.WAIT)
        self.assertEqual(state.key_pressed("2"), MODULE.Decision.UNLOCK)
        self.assertNotIn("8642", str(policy.to_json()))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            MODULE._atomic_json_write(path, policy.to_json())
            restored = MODULE.Policy.from_json(json.loads(path.read_text()))
        self.assertTrue(restored.matches_prefix("864", 3))

    def test_unrelated_keys_lock_only_at_the_configured_limit(self) -> None:
        state = MODULE.InputState(self.policy())

        self.assertEqual(state.key_pressed("x"), MODULE.Decision.WAIT)
        self.assertEqual(state.key_pressed("y"), MODULE.Decision.WAIT)
        self.assertEqual(state.key_pressed("z"), MODULE.Decision.LOCK)

    def test_only_distinct_corner_contacts_accumulate(self) -> None:
        state = MODULE.InputState(self.policy())

        self.assertEqual(state.pointer_motion("a", 1, 1, 1000, 700), MODULE.Decision.WAIT)
        self.assertEqual(state.pointer_motion("a", 40, 40, 1000, 700), MODULE.Decision.WAIT)
        self.assertEqual(state.pointer_motion("a", 1, 1, 1000, 700), MODULE.Decision.WAIT)
        self.assertEqual(state.pointer_motion("a", 999, 1, 1000, 700), MODULE.Decision.WAIT)
        self.assertEqual(state.pointer_motion("a", 999, 699, 1000, 700), MODULE.Decision.UNLOCK)

    def test_small_jitter_is_tolerated_but_deliberate_reversal_locks(self) -> None:
        state = MODULE.InputState(self.policy())

        self.assertEqual(state.pointer_motion("a", 400, 300, 1000, 700), MODULE.Decision.WAIT)
        self.assertEqual(state.pointer_motion("a", 500, 300, 1000, 700), MODULE.Decision.WAIT)
        self.assertEqual(state.pointer_motion("a", 470, 302, 1000, 700), MODULE.Decision.WAIT)
        self.assertEqual(state.pointer_motion("a", 435, 300, 1000, 700), MODULE.Decision.LOCK)


if __name__ == "__main__":
    unittest.main()
