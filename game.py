from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from cards import Card, Deck, RANKS
from bots import BotBase, PublicState
from replay import ReplayRecorder, build_initial_state


@dataclass
class PlayerState:
    hand: List[Card]
    bot: BotBase
    placement: Optional[int] = None


@dataclass
class GameLogEvent:
    message: str


@dataclass
class GameState:
    players: List[PlayerState]
    rng_seed: Optional[int]
    active_rank: Optional[str] = None
    pile: List[Card] = field(default_factory=list)
    current_player: int = 0
    placements: List[int] = field(default_factory=list)
    known_discarded: Dict[str, int] = field(default_factory=lambda: {rank: 0 for rank in RANKS})
    known_revealed: Dict[str, int] = field(default_factory=lambda: {rank: 0 for rank in RANKS})
    turn_count: int = 0
    pile_pickups: List[int] = field(default_factory=list)
    challenge_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    log: List[GameLogEvent] = field(default_factory=list)

    def active_players(self) -> List[int]:
        return [idx for idx, player in enumerate(self.players) if player.placement is None]

    def hand_sizes(self) -> Dict[int, int]:
        return {idx: len(player.hand) for idx, player in enumerate(self.players)}

    def add_log(self, message: str) -> None:
        self.log.append(GameLogEvent(message=message))


class Game:
    def __init__(
        self,
        players: List[BotBase],
        rng_seed: Optional[int] = None,
        recorder: Optional[ReplayRecorder] = None,
    ) -> None:
        self.rng_seed = rng_seed
        self.players = players
        self.recorder = recorder

    def setup(self) -> GameState:
        import random

        rng = random.Random(self.rng_seed)
        deck = Deck(rng)
        deck.shuffle()
        hands = deck.deal(len(self.players))
        state_players = [PlayerState(hand=hand, bot=bot) for hand, bot in zip(hands, self.players)]
        challenge_stats: Dict[str, Dict[str, int]] = {}
        for bot in self.players:
            challenge_stats.setdefault(
                bot.name, {"opportunities": 0, "attempts": 0, "success": 0}
            )
        return GameState(
            players=state_players,
            rng_seed=self.rng_seed,
            challenge_stats=challenge_stats,
        )

    def play_game(self, verbose: bool = False) -> GameState:
        state = self.setup()
        if self.recorder is not None:
            bot_types = [player.bot.name for player in state.players]
            initial_state = build_initial_state([player.hand for player in state.players], bot_types)
            self.recorder.set_initial_state(initial_state)
            self.recorder.record_event("GAME_START")
        active_order = list(range(len(state.players)))
        state.current_player = 0
        self._resolve_discard_quads(state, verbose)
        while len(state.placements) < len(state.players):
            if not active_order:
                break
            current_idx = active_order[state.current_player]
            player = state.players[current_idx]
            if player.placement is not None:
                state.current_player = (state.current_player + 1) % len(active_order)
                continue
            self._take_turn(state, current_idx, active_order, verbose)
            active_order = [idx for idx in active_order if state.players[idx].placement is None]
            if not active_order:
                break
            if state.current_player >= len(active_order):
                state.current_player = 0
        if len(state.placements) < len(state.players):
            remaining = [idx for idx in range(len(state.players)) if idx not in state.placements]
            for idx in remaining:
                state.placements.append(idx)
                state.players[idx].placement = len(state.placements)
                if self.recorder is not None:
                    self.recorder.record_event(
                        "PLACEMENT", player=idx, place=state.players[idx].placement
                    )
        if self.recorder is not None:
            self.recorder.record_event("GAME_END", placements=state.placements)
        return state

    def _take_turn(
        self,
        state: GameState,
        player_idx: int,
        active_order: List[int],
        verbose: bool,
    ) -> None:
        player = state.players[player_idx]
        public = PublicState(
            active_rank=state.active_rank,
            pile_size=len(state.pile),
            hand_sizes=state.hand_sizes(),
            known_discarded=state.known_discarded.copy(),
            known_revealed=state.known_revealed.copy(),
            last_play_count=0,
            last_player_id=None,
        )
        if state.active_rank is None:
            chosen_rank = player.bot.choose_active_rank(player.hand, public)
            state.active_rank = chosen_rank
            if verbose:
                state.add_log(f"P{player_idx} selects active rank {chosen_rank}.")
            if self.recorder is not None:
                self.recorder.record_event("SELECT_RANK", player=player_idx, rank=chosen_rank)
        public = PublicState(
            active_rank=state.active_rank,
            pile_size=len(state.pile),
            hand_sizes=state.hand_sizes(),
            known_discarded=state.known_discarded.copy(),
            known_revealed=state.known_revealed.copy(),
            last_play_count=0,
            last_player_id=None,
        )
        played_cards, claim_rank = player.bot.choose_play(player.hand, public)
        if claim_rank != state.active_rank:
            raise ValueError("Claimed rank must match active rank")
        if not 1 <= len(played_cards) <= 3:
            raise ValueError("Must play 1-3 cards")
        for card in played_cards:
            if card not in player.hand:
                raise ValueError("Player tried to play a card not in hand")
        for card in played_cards:
            player.hand.remove(card)
            state.pile.append(card)
        state.turn_count += 1
        if verbose:
            state.add_log(
                f"P{player_idx} plays {len(played_cards)} claiming {claim_rank} (pile={len(state.pile)})"
            )
            self._log_hand_sizes(state)
        if self.recorder is not None:
            self.recorder.record_event(
                "PLAY", player=player_idx, claim_rank=claim_rank, cards=played_cards
            )
        self._check_wins(state, verbose)
        self._resolve_discard_quads(state, verbose)
        next_player_idx = self._next_player(active_order, player_idx)
        if next_player_idx is None:
            return
        next_player = state.players[next_player_idx]
        public_after_play = PublicState(
            active_rank=state.active_rank,
            pile_size=len(state.pile),
            hand_sizes=state.hand_sizes(),
            known_discarded=state.known_discarded.copy(),
            known_revealed=state.known_revealed.copy(),
            last_play_count=len(played_cards),
            last_player_id=player_idx,
        )
        state.challenge_stats[next_player.bot.name]["opportunities"] += 1
        challenge = next_player.bot.should_challenge(next_player.hand, public_after_play)
        debug_line = getattr(next_player.bot, "last_challenge_debug", None)
        if debug_line:
            if verbose:
                state.add_log(f"Challenge eval: {debug_line}")
            if self.recorder is not None:
                self.recorder.record_event(
                    "CHALLENGE_EVAL", challenger=next_player_idx, message=debug_line
                )
        if self.recorder is not None:
            self.recorder.record_event(
                "CHALLENGE_DECISION", challenger=next_player_idx, challenge=challenge
            )
        if challenge:
            state.challenge_stats[next_player.bot.name]["attempts"] += 1
            truthful = all(card.rank == state.active_rank for card in played_cards)
            if not truthful:
                state.challenge_stats[next_player.bot.name]["success"] += 1
            if verbose:
                state.add_log(
                    f"P{next_player_idx} challenges -> {'TRUTH' if truthful else 'LIE'}"
                )
                revealed = ", ".join(str(card) for card in played_cards)
                state.add_log(f"Revealed: {revealed}")
            if self.recorder is not None:
                self.recorder.record_event(
                    "CHALLENGE_RESOLUTION",
                    challenger=next_player_idx,
                    truthful=truthful,
                    revealed=played_cards,
                )
            for card in played_cards:
                state.known_revealed[card.rank] += 1
            if truthful:
                picker = next_player_idx
            else:
                picker = player_idx
            pickup_size = len(state.pile)
            state.pile_pickups.append(pickup_size)
            if self.recorder is not None:
                self.recorder.record_event("PICKUP_PILE", player=picker, cards=state.pile.copy())
            state.players[picker].hand.extend(state.pile)
            state.pile.clear()
            if verbose:
                state.add_log(f"P{picker} picks up {pickup_size} cards. Pile cleared.")
                self._log_hand_sizes(state)
            state.active_rank = None
            self._check_wins(state, verbose)
            self._resolve_discard_quads(state, verbose)
            next_turn_player = self._next_player(active_order, picker)
            if next_turn_player is None:
                return
            state.current_player = active_order.index(next_turn_player)
        else:
            if verbose:
                state.add_log(f"P{next_player_idx} does not challenge.")
            state.current_player = (state.current_player + 1) % len(active_order)

    def _next_player(self, active_order: List[int], current_idx: int) -> Optional[int]:
        if not active_order:
            return None
        if current_idx not in active_order:
            return active_order[0]
        idx = active_order.index(current_idx)
        return active_order[(idx + 1) % len(active_order)]

    def _resolve_discard_quads(self, state: GameState, verbose: bool) -> None:
        changed = True
        while changed:
            changed = False
            for idx, player in enumerate(state.players):
                if player.placement is not None:
                    continue
                counts: Dict[str, List[Card]] = {rank: [] for rank in RANKS}
                for card in player.hand:
                    counts[card.rank].append(card)
                for rank, cards in counts.items():
                    if rank == "A":
                        continue
                    if len(cards) == 4:
                        for card in cards:
                            player.hand.remove(card)
                        state.known_discarded[rank] += 4
                        changed = True
                        if verbose:
                            state.add_log(f"P{idx} discards four {rank}s.")
                            self._log_hand_sizes(state)
                        if self.recorder is not None:
                            self.recorder.record_event(
                                "DISCARD_QUAD", player=idx, rank=rank, cards=cards
                            )
                        self._check_wins(state, verbose)
                        break
                if changed:
                    break

    def _check_wins(self, state: GameState, verbose: bool) -> None:
        for idx, player in enumerate(state.players):
            if player.placement is None and len(player.hand) == 0:
                state.placements.append(idx)
                player.placement = len(state.placements)
                if verbose:
                    state.add_log(f"P{idx} finishes in place {player.placement}.")
                if self.recorder is not None:
                    self.recorder.record_event(
                        "PLACEMENT", player=idx, place=player.placement
                    )

    def _log_hand_sizes(self, state: GameState) -> None:
        sizes = " ".join(f"P{idx}:{len(player.hand)}" for idx, player in enumerate(state.players))
        state.add_log(f"Hand sizes -> {sizes}")
