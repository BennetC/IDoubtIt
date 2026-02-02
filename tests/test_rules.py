import unittest

from cards import Card
from game import Game
from bots import BotBase, PublicState


class ScriptedBot(BotBase):
    name = "scripted"

    def __init__(self, plays, challenges):
        import random

        super().__init__(random.Random(0))
        self._plays = plays
        self._challenges = challenges
        self._play_idx = 0
        self._challenge_idx = 0

    def choose_active_rank(self, hand, public: PublicState):
        return self._plays[self._play_idx][1]

    def choose_play(self, hand, public: PublicState):
        cards, claim = self._plays[self._play_idx]
        self._play_idx += 1
        return cards, claim

    def should_challenge(self, hand, public: PublicState) -> bool:
        value = self._challenges[self._challenge_idx]
        self._challenge_idx += 1
        return value


class RuleInvariantTests(unittest.TestCase):
    def test_pile_clears_on_challenge(self):
        bot0 = ScriptedBot([( [Card("3", "♣")], "2")], [])
        bot1 = ScriptedBot([], [True])
        game = Game([bot0, bot1])
        state = game.setup()
        state.players[0].hand = [Card("3", "♣")]
        state.players[1].hand = [Card("2", "♦")]
        state.active_rank = "2"
        game._take_turn(state, 0, [0, 1], verbose=False)
        self.assertEqual(state.pile, [])
        self.assertIsNone(state.active_rank)
        self.assertEqual(len(state.players[0].hand), 1)

    def test_only_next_player_can_challenge(self):
        bot0 = ScriptedBot([( [Card("2", "♣")], "2")], [])
        bot1 = ScriptedBot([], [False])
        bot2 = ScriptedBot([], [True])
        game = Game([bot0, bot1, bot2])
        state = game.setup()
        state.players[0].hand = [Card("2", "♣")]
        state.players[1].hand = [Card("3", "♦")]
        state.players[2].hand = [Card("4", "♥")]
        state.active_rank = "2"
        game._take_turn(state, 0, [0, 1, 2], verbose=False)
        self.assertEqual(state.challenge_stats["scripted"]["attempts"], 0)
        self.assertEqual(state.challenge_stats["scripted"]["opportunities"], 1)

    def test_discard_loop_and_win_check(self):
        bot0 = ScriptedBot([], [])
        bot1 = ScriptedBot([], [])
        game = Game([bot0, bot1])
        state = game.setup()
        state.players[0].hand = [
            Card("5", "♣"),
            Card("5", "♦"),
            Card("5", "♥"),
            Card("5", "♠"),
            Card("6", "♣"),
            Card("6", "♦"),
            Card("6", "♥"),
            Card("6", "♠"),
        ]
        state.players[1].hand = [Card("2", "♣")]
        game._resolve_discard_quads(state, verbose=False)
        self.assertEqual(len(state.players[0].hand), 0)
        self.assertEqual(state.players[0].placement, 1)

    def test_challenge_failure_counts(self):
        bot0 = ScriptedBot([([Card("2", "♣")], "2")], [])
        bot1 = ScriptedBot([], [True])
        game = Game([bot0, bot1])
        state = game.setup()
        state.players[0].hand = [Card("2", "♣")]
        state.players[1].hand = [Card("3", "♦")]
        state.active_rank = "2"
        game._take_turn(state, 0, [0, 1], verbose=False)
        stats = state.challenge_stats["scripted"]
        self.assertEqual(stats["attempts"], 1)
        self.assertEqual(stats["success"], 0)
        self.assertEqual(stats["failure"], 1)


if __name__ == "__main__":
    unittest.main()
