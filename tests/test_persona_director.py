import unittest

from castle.server.persona_director import build_director_contract, decide_persona_state


class PersonaDirectorTests(unittest.TestCase):
    def test_private_care_stays_fast_and_warm(self):
        decision = decide_persona_state({"transcript": "我今天真的很累，陪我一下"})

        self.assertEqual(decision.state, "private_care")
        self.assertEqual(decision.realtime.lane, "fast")
        self.assertFalse(decision.claude.should_call)
        self.assertEqual(decision.intimacy_level, 3)
        self.assertEqual(decision.avatar.expression, "soft")

    def test_work_request_routes_to_deep_lane(self):
        decision = decide_persona_state({"transcript": "幫我規劃 Slack agent 的下一步"})

        self.assertEqual(decision.state, "work_focus")
        self.assertEqual(decision.realtime.lane, "deep")
        self.assertTrue(decision.claude.should_call)
        self.assertIn("Deep work request", decision.claude.brief)

    def test_high_risk_reduces_intimacy_and_requires_confirmation(self):
        decision = decide_persona_state({"transcript": "幫我刪除這份合約並發送給客戶"})

        self.assertEqual(decision.state, "high_risk")
        self.assertEqual(decision.risk_level, "high")
        self.assertEqual(decision.intimacy_level, 0)
        self.assertTrue(decision.claude.should_call)
        self.assertIn("confirmation", decision.claude.safety_posture)

    def test_director_contract_mentions_realtime_and_risk(self):
        contract = build_director_contract()

        self.assertIn("Realtime", contract)
        self.assertIn("high-risk", contract)
        self.assertIn("Claude", contract)

    def test_care_then_work_acknowledges_fatigue_before_task(self):
        decision = decide_persona_state({"transcript": "我好累，但幫我看一下 slack"})

        # still routes the work, but voice + brain lead with the person
        self.assertEqual(decision.state, "work_focus")
        self.assertTrue(decision.claude.should_call)
        self.assertIn("care-then-work blend", decision.reasons)
        self.assertIn("tired", decision.claude.safety_posture)
        self.assertGreaterEqual(decision.intimacy_level, 2)

    def test_intimacy_cap_clamps_warmth(self):
        decision = decide_persona_state(
            {"transcript": "陪我一下", "requested_intimacy": 1}
        )

        self.assertEqual(decision.state, "private_care")
        self.assertEqual(decision.intimacy_level, 1)
        self.assertTrue(any("intimacy capped" in r for r in decision.reasons))

    def test_intimacy_tone_is_graduated_in_voice(self):
        warm = decide_persona_state({"transcript": "陪我一下"})
        capped = decide_persona_state(
            {"transcript": "陪我一下", "requested_intimacy": 0}
        )

        self.assertIn("fond", warm.realtime.style)
        self.assertNotEqual(warm.realtime.style, capped.realtime.style)

    def test_sticky_prev_state_avoids_whiplash(self):
        # a neutral filler turn should not yank Sophie out of private_care
        decision = decide_persona_state(
            {"transcript": "嗯嗯", "prev_state": "private_care"}
        )

        self.assertEqual(decision.state, "private_care")
        self.assertIn("sticky from prev_state", decision.reasons)

    def test_neutral_turn_without_history_is_listening(self):
        decision = decide_persona_state({"transcript": "嗯嗯"})

        self.assertEqual(decision.state, "listening")


if __name__ == "__main__":
    unittest.main()
