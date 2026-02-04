from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Dict, List, Optional, Tuple, TypedDict

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
        self.last_challenge_eval: Optional[ChallengeEval] = None

    def choose_active_rank(self, hand: List[Card], public: PublicState) -> str:
        raise NotImplementedError

    def choose_play(
        self, hand: List[Card], public: PublicState
    ) -> Tuple[List[Card], str]:
        raise NotImplementedError

    def should_challenge(self, hand: List[Card], public: PublicState) -> bool:
        raise NotImplementedError


def p_truthful_play(
    opponent_hand_size: int,
    my_count_active: int,
    known_out_of_play_active: int,
    k: int,
    my_hand_size: int,
    known_out_of_play_total: int,
) -> float:
    if opponent_hand_size <= 0 or k <= 0:
        return 0.0
    total_active = 4
    available_active_for_others = total_active - known_out_of_play_active - my_count_active
    if available_active_for_others < k:
        return 0.0
    unknown_cards_outside_me = 52 - my_hand_size - known_out_of_play_total
    if unknown_cards_outside_me <= 0:
        return 0.0
    if opponent_hand_size > unknown_cards_outside_me:
        opponent_hand_size = unknown_cards_outside_me
    if opponent_hand_size < k:
        return 0.0
    try:
        numerator = math.comb(available_active_for_others, k) * math.comb(
            unknown_cards_outside_me - available_active_for_others,
            opponent_hand_size - k,
        )
        denominator = math.comb(unknown_cards_outside_me, opponent_hand_size)
    except ValueError:
        return 0.0
    if denominator == 0:
        return 0.0
    return min(1.0, numerator / denominator)


def _known_out_of_play_total(public: PublicState) -> int:
    return sum(public.known_discarded.values()) + sum(public.known_revealed.values())


class ChallengeEval(TypedDict):
    p_truthful: float
    u_challenge: float
    u_pass: float
    pile: int
    k: int
    my_active: int
    opp_hand: int


def _build_challenge_eval(
    p_truthful: float,
    u_challenge: float,
    u_pass: float,
    pile_size: int,
    k: int,
    my_count_active: int,
    opponent_hand_size: int,
) -> ChallengeEval:
    return {
        "p_truthful": p_truthful,
        "u_challenge": u_challenge,
        "u_pass": u_pass,
        "pile": pile_size,
        "k": k,
        "my_active": my_count_active,
        "opp_hand": opponent_hand_size,
    }


def format_challenge_eval_line(eval_data: ChallengeEval) -> str:
    return (
        f"p_truthful={eval_data['p_truthful']:.2f}, "
        f"U_challenge={eval_data['u_challenge']:.2f}, "
        f"U_pass={eval_data['u_pass']:.2f}, "
        f"pile={eval_data['pile']}, k={eval_data['k']}, "
        f"my_active={eval_data['my_active']}, opp_hand={eval_data['opp_hand']}"
    )


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
        decision = self.rng.random() < max(0.05, base - adjustment)
        known_active = public.known_discarded.get(active_rank, 0) + public.known_revealed.get(
            active_rank, 0
        )
        opponent_size = public.hand_sizes.get(public.last_player_id, 0)
        p_truthful = p_truthful_play(
            opponent_hand_size=opponent_size,
            my_count_active=count_active,
            known_out_of_play_active=known_active,
            k=public.last_play_count,
            my_hand_size=len(hand),
            known_out_of_play_total=_known_out_of_play_total(public),
        )
        u_challenge = pile_size * (1 - 2 * p_truthful)
        u_pass = 0.2 * pile_size - 0.5
        self.last_challenge_eval = _build_challenge_eval(
            p_truthful,
            u_challenge,
            u_pass,
            pile_size,
            public.last_play_count,
            count_active,
            opponent_size,
        )
        return decision


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
        known_out_of_play_active = public.known_discarded.get(
            active_rank, 0
        ) + public.known_revealed.get(active_rank, 0)
        opponent_size = public.hand_sizes.get(public.last_player_id, 0)
        k = public.last_play_count
        if opponent_size <= 0 or k <= 0:
            return False
        p_truthful = p_truthful_play(
            opponent_hand_size=opponent_size,
            my_count_active=known_in_hand,
            known_out_of_play_active=known_out_of_play_active,
            k=k,
            my_hand_size=len(hand),
            known_out_of_play_total=_known_out_of_play_total(public),
        )
        pile_size = public.pile_size
        min_opp_cards = min(public.hand_sizes.values()) if public.hand_sizes else opponent_size
        tempo_bonus = max(3.0, pile_size / 2)
        tempo_penalty = tempo_bonus if min_opp_cards <= 3 else 0.0
        u_challenge = pile_size * (1 - 2 * p_truthful) - tempo_penalty
        if len(hand) <= 3 and p_truthful > 0.2 and pile_size < 8:
            u_challenge -= 1.5
        alpha = 0.2
        beta = 0.5
        u_pass = alpha * pile_size - beta
        if min_opp_cards <= 3:
            u_pass += tempo_bonus
        desperate = len(hand) >= 8 and pile_size >= 8
        if p_truthful == 0:
            decision = True
        elif p_truthful > 0.65 and not desperate:
            decision = False
        else:
            decision = u_challenge > u_pass
        self.last_challenge_eval = _build_challenge_eval(
            p_truthful,
            u_challenge,
            u_pass,
            pile_size,
            k,
            known_in_hand,
            opponent_size,
        )
        return decision


class HumanWebPlayer(BotBase):
    name = "human"

    def choose_active_rank(self, hand: List[Card], public: PublicState) -> str:
        raise RuntimeError("HumanWebPlayer requires web input for active rank.")

    def choose_play(
        self, hand: List[Card], public: PublicState
    ) -> Tuple[List[Card], str]:
        raise RuntimeError("HumanWebPlayer requires web input for play.")

    def should_challenge(self, hand: List[Card], public: PublicState) -> bool:
        raise RuntimeError("HumanWebPlayer requires web input for challenge.")


BOT_TYPES = {
    "random": RandomBot,
    "heuristic": HeuristicBot,
}
