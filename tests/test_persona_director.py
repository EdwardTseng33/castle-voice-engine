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


if __name__ == "__main__":
    unittest.main()
