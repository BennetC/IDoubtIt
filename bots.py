from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Dict, List, Optional, Tuple

from cards import Card, RANKS


@dataclass(frozen=True)
class PublicState:
    active_rank: Optional[str]
    pile_size: int
    hand_sizes: Dict[int, int]
    known_discarded: Dict[str, int]
    known_revealed: Dict[str, int]
    last_play_count: int
    last_player_id: Optional[int]


class BotBase:
    name = "base"

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def choose_active_rank(self, hand: List[Card], public: PublicState) -> str:
        raise NotImplementedError

    def choose_play(
        self, hand: List[Card], public: PublicState
    ) -> Tuple[List[Card], str]:
        raise NotImplementedError

    def should_challenge(self, hand: List[Card], public: PublicState) -> bool:
        raise NotImplementedError


class RandomBot(BotBase):
    name = "random"

    def choose_active_rank(self, hand: List[Card], public: PublicState) -> str:
        return self.rng.choice(RANKS)

    def choose_play(
        self, hand: List[Card], public: PublicState
    ) -> Tuple[List[Card], str]:
        count = min(len(hand), self.rng.choice([1, 2, 3]))
        chosen = self.rng.sample(hand, count)
        claim_rank = public.active_rank or self.choose_active_rank(hand, public)
        return chosen, claim_rank

    def should_challenge(self, hand: List[Card], public: PublicState) -> bool:
        active_rank = public.active_rank
        if active_rank is None:
            return False
        count_active = sum(1 for card in hand if card.rank == active_rank)
        pile_size = public.pile_size
        base = min(0.6, 0.1 + pile_size / 40)
        adjustment = max(0.0, 0.08 * count_active)
        return self.rng.random() < max(0.05, base - adjustment)


class HeuristicBot(BotBase):
    name = "heuristic"

    def choose_active_rank(self, hand: List[Card], public: PublicState) -> str:
        counts = {rank: 0 for rank in RANKS}
        for card in hand:
            counts[card.rank] += 1
        best = max(counts.values())
        candidates = [rank for rank, count in counts.items() if count == best]
        non_aces = [rank for rank in candidates if rank != "A"]
        if non_aces:
            candidates = non_aces
        return self.rng.choice(candidates)

    def choose_play(
        self, hand: List[Card], public: PublicState
    ) -> Tuple[List[Card], str]:
        active_rank = public.active_rank or self.choose_active_rank(hand, public)
        truthful = [card for card in hand if card.rank == active_rank]
        if truthful:
            count = min(len(truthful), 3)
            chosen = truthful[:count]
            return chosen, active_rank
        # Bluffing: prefer shedding aces, otherwise ranks held most.
        aces = [card for card in hand if card.rank == "A"]
        if aces:
            chosen = [aces[0]]
            return chosen, active_rank
        counts: Dict[str, int] = {rank: 0 for rank in RANKS}
        for card in hand:
            counts[card.rank] += 1
        max_rank = max(counts, key=lambda rank: counts[rank])
        chosen = [card for card in hand if card.rank == max_rank][:2]
        if not chosen:
            chosen = [hand[0]]
        return chosen, active_rank

    def should_challenge(self, hand: List[Card], public: PublicState) -> bool:
        active_rank = public.active_rank
        if active_rank is None:
            return False
        known_in_hand = sum(1 for card in hand if card.rank == active_rank)
        remaining = 4 - known_in_hand
        remaining -= public.known_discarded.get(active_rank, 0)
        remaining -= public.known_revealed.get(active_rank, 0)
        remaining = max(0, remaining)
        opponent_size = public.hand_sizes.get(public.last_player_id, 0)
        k = public.last_play_count
        # Approximate probability: assume opponent hand is uniform unknown cards.
        if opponent_size <= 0 or k <= 0:
            return False
        prob_truth = 1.0
        for i in range(k):
            denom = max(1, opponent_size - i)
            prob_truth *= min(1.0, (remaining - i) / denom)
        pile_penalty = 0.6 * public.pile_size
        # Risk adjustment if opponent is near empty and pile is large.
        risk = 0.0
        if opponent_size <= 3 and public.pile_size >= 6:
            risk = 1.5
        expected_gain = (1 - prob_truth) * public.pile_size - prob_truth * pile_penalty
        return expected_gain > risk


BOT_TYPES = {
    "random": RandomBot,
    "heuristic": HeuristicBot,
}
