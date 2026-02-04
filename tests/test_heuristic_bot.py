import unittest

from bots import HeuristicBot, PublicState, p_truthful_play
from cards import Card, RANKS


def _blank_known() -> dict:
    return {rank: 0 for rank in RANKS}


class HeuristicBotChallengeTests(unittest.TestCase):
    def test_challenge_when_opponent_cannot_play_two(self):
        import random

        bot = HeuristicBot(random.Random(0))
        hand = [Card("9", "♣"), Card("9", "♦"), Card("9", "♥")]
        public = PublicState(
            active_rank="9",
            pile_size=5,
            hand_sizes={0: len(hand), 1: 5},
            known_discarded=_blank_known(),
            known_revealed=_blank_known(),
            last_play_count=2,
            last_player_id=1,
        )
        self.assertTrue(bot.should_challenge(hand, public))

    def test_p_truthful_decreases_with_k(self):
        p_k1 = p_truthful_play(
            opponent_hand_size=5,
            my_count_active=1,
            known_out_of_play_active=0,
            k=1,
            my_hand_size=5,
            known_out_of_play_total=0,
        )
        p_k2 = p_truthful_play(
            opponent_hand_size=5,
            my_count_active=1,
            known_out_of_play_active=0,
            k=2,
            my_hand_size=5,
            known_out_of_play_total=0,
        )
        self.assertLess(p_k2, p_k1)

    def test_pass_when_truth_probability_high_and_pile_small(self):
        import random

        bot = HeuristicBot(random.Random(0))
        hand = [
            Card("2", "♣"),
            Card("3", "♦"),
            Card("4", "♥"),
            Card("5", "♠"),
            Card("6", "♣"),
        ]
        known_discarded = _blank_known()
        ranks = [rank for rank in RANKS if rank != "9"]
        for rank in ranks[:10]:
            known_discarded[rank] = 4
        known_discarded[ranks[10]] = 3
        public = PublicState(
            active_rank="9",
            pile_size=2,
            hand_sizes={0: len(hand), 1: 2},
            known_discarded=known_discarded,
            known_revealed=_blank_known(),
            last_play_count=2,
            last_player_id=1,
        )
        self.assertFalse(bot.should_challenge(hand, public))


if __name__ == "__main__":
    unittest.main()
