import unittest

from replay import serialize_card
from web_session import GameSession


def snapshot_state(session: GameSession) -> dict:
    return {
        "active_rank": session.state.active_rank,
        "current_player": session.state.current_player,
        "placements": list(session.state.placements),
        "pile": [serialize_card(card) for card in session.state.pile],
        "hands": [
            [serialize_card(card) for card in player.hand] for player in session.state.players
        ],
    }


def advance_with_action(session: GameSession) -> None:
    decision = session.pending_decision
    if decision is None:
        session.step()
        return
    if decision.decision_type == "SELECT_RANK":
        session.apply_action({"type": "SELECT_RANK", "rank": "2"})
    elif decision.decision_type == "PLAY":
        cards = session.state.players[session.human_index].hand[:1]
        session.apply_action(
            {"type": "PLAY", "cards": [serialize_card(card) for card in cards]}
        )
    elif decision.decision_type == "CHALLENGE":
        session.apply_action({"type": "CHALLENGE", "value": False})
    session.step()


class WebSessionTests(unittest.TestCase):
    def test_save_load_determinism(self) -> None:
        session = GameSession(
            player_count=3,
            human_index=0,
            bot_types=["human", "random", "random"],
            seed=123,
        )
        session.step()
        advance_with_action(session)
        advance_with_action(session)
        save_data = session.to_save_dict()
        loaded = GameSession.from_save_dict(save_data)
        for _ in range(3):
            advance_with_action(session)
            advance_with_action(loaded)
        self.assertEqual(snapshot_state(session), snapshot_state(loaded))

    def test_illegal_play_rejected(self) -> None:
        session = GameSession(
            player_count=2,
            human_index=0,
            bot_types=["human", "random"],
            seed=5,
        )
        session.step()
        session.apply_action({"type": "SELECT_RANK", "rank": "K"})
        cards = session.state.players[session.human_index].hand[:4]
        with self.assertRaises(ValueError):
            session.apply_action(
                {"type": "PLAY", "cards": [serialize_card(card) for card in cards]}
            )

    def test_step_halts_for_human_decisions(self) -> None:
        session = GameSession(
            player_count=3,
            human_index=1,
            bot_types=["random", "human", "random"],
            seed=42,
        )
        events = session.step()
        self.assertTrue(events)
        self.assertIsNotNone(session.pending_decision)
        self.assertEqual(session.pending_decision.decision_type, "CHALLENGE")


if __name__ == "__main__":
    unittest.main()
