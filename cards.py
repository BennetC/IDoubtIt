from __future__ import annotations

from dataclasses import dataclass
import random
from typing import List

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♣", "♦", "♥", "♠"]


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


class Deck:
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self.cards = [Card(rank, suit) for rank in RANKS for suit in SUITS]

    def shuffle(self) -> None:
        self._rng.shuffle(self.cards)

    def deal(self, num_players: int) -> List[List[Card]]:
        if num_players < 2 or num_players > 6:
            raise ValueError("num_players must be between 2 and 6")
        hands = [[] for _ in range(num_players)]
        for idx, card in enumerate(self.cards):
            hands[idx % num_players].append(card)
        return hands
