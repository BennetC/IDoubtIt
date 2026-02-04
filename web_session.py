from __future__ import annotations

from dataclasses import dataclass
import json
import os
import random
import uuid
from typing import Any, Dict, List, Optional

from bots import BOT_TYPES, BotBase, HumanWebPlayer, PublicState
from cards import Card, RANKS
from game import Game, GameState, PlayerState
from replay import (
    ReplayRecorder,
    build_initial_state,
    build_metadata,
    parse_card,
    serialize_card,
    state_from_dict,
    state_to_dict,
)


@dataclass
class PendingDecision:
    decision_type: str
    player: int

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.decision_type, "player": self.player}


def _jsonify(obj: Any) -> Any:
    if isinstance(obj, tuple):
        return [_jsonify(item) for item in obj]
    if isinstance(obj, list):
        return [_jsonify(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _jsonify(value) for key, value in obj.items()}
    return obj


def _tuplefy(obj: Any) -> Any:
    if isinstance(obj, list):
        return tuple(_tuplefy(item) for item in obj)
    if isinstance(obj, dict):
        return {key: _tuplefy(value) for key, value in obj.items()}
    return obj


def _bot_from_type(name: str, rng: random.Random) -> BotBase:
    if name == "human":
        return HumanWebPlayer(rng)
    bot_cls = BOT_TYPES.get(name)
    if bot_cls is None:
        raise ValueError(f"Unknown bot type: {name}")
    return bot_cls(rng)


def _state_to_dict(state: GameState) -> Dict[str, Any]:
    return {
        "players": [
            {
                "hand": [serialize_card(card) for card in player.hand],
                "bot": player.bot.name,
                "placement": player.placement,
            }
            for player in state.players
        ],
        "rng_seed": state.rng_seed,
        "active_rank": state.active_rank,
        "pile": [serialize_card(card) for card in state.pile],
        "current_player": state.current_player,
        "placements": list(state.placements),
        "known_discarded": dict(state.known_discarded),
        "known_revealed": dict(state.known_revealed),
        "turn_count": state.turn_count,
        "pile_pickups": list(state.pile_pickups),
        "challenge_stats": json.loads(json.dumps(state.challenge_stats)),
    }


def _state_from_dict(data: Dict[str, Any], bots: List[BotBase]) -> GameState:
    players: List[PlayerState] = []
    for idx, player_data in enumerate(data["players"]):
        hand = [parse_card(card) for card in player_data.get("hand", [])]
        placement = player_data.get("placement")
        players.append(PlayerState(hand=hand, bot=bots[idx], placement=placement))
    return GameState(
        players=players,
        rng_seed=data.get("rng_seed"),
        active_rank=data.get("active_rank"),
        pile=[parse_card(card) for card in data.get("pile", [])],
        current_player=data.get("current_player", 0),
        placements=list(data.get("placements", [])),
        known_discarded=dict(data.get("known_discarded", {})),
        known_revealed=dict(data.get("known_revealed", {})),
        turn_count=data.get("turn_count", 0),
        pile_pickups=list(data.get("pile_pickups", [])),
        challenge_stats=dict(data.get("challenge_stats", {})),
    )


class GameSession:
    def __init__(
        self,
        player_count: int,
        human_index: int,
        bot_types: List[str],
        seed: Optional[int],
    ) -> None:
        self.session_id = uuid.uuid4().hex
        self.seed = seed
        self.human_index = human_index
        self.bot_types = list(bot_types)
        self.paused = False
        self.finished = False
        self.pending_decision: Optional[PendingDecision] = None
        self.last_played_cards: List[Card] = []
        self.last_played_player: Optional[int] = None
        self.replay_saved = False

        master_rng = random.Random(seed)
        self.bot_rngs: List[Optional[random.Random]] = []
        bots: List[BotBase] = []
        for idx in range(player_count):
            rng = random.Random(master_rng.randint(0, 1_000_000))
            self.bot_rngs.append(rng)
            bots.append(_bot_from_type(bot_types[idx], rng))

        metadata = build_metadata(seed, player_count, [bot.name for bot in bots])
        self.recorder = ReplayRecorder(metadata=metadata, snapshot_interval=10)

        self.engine = Game(bots, rng_seed=seed, recorder=self.recorder)
        self.state = self.engine.setup()
        initial_state = build_initial_state([player.hand for player in self.state.players], bot_types)
        self.recorder.set_initial_state(initial_state)
        self.recorder.record_event("GAME_START")
        self.active_order = [idx for idx in range(player_count)]
        self.state.current_player = self.active_order[0] if self.active_order else None
        self.engine._resolve_discard_quads(self.state, verbose=False)
        self._refresh_active_order()

    def _refresh_active_order(self) -> None:
        self.active_order = [
            idx for idx in self.active_order if self.state.players[idx].placement is None
        ]
        if not self.active_order:
            self.state.current_player = None
            return
        if self.state.current_player not in self.active_order:
            self.state.current_player = self.active_order[0]

    def _finalize_if_needed(self) -> None:
        if len(self.state.placements) >= len(self.state.players):
            if not self.finished:
                self.recorder.record_event("GAME_END", placements=self.state.placements)
            self.finished = True
            self.state.current_player = None
            return
        if not self.active_order:
            remaining = [
                idx for idx in range(len(self.state.players)) if idx not in self.state.placements
            ]
            for idx in remaining:
                self.state.placements.append(idx)
                self.state.players[idx].placement = len(self.state.placements)
                self.recorder.record_event(
                    "PLACEMENT", player=idx, place=self.state.players[idx].placement
                )
            self.recorder.record_event("GAME_END", placements=self.state.placements)
            self.finished = True
            self.state.current_player = None

    def _public_state(self, reveal_all: bool) -> Dict[str, Any]:
        players = []
        for idx, player in enumerate(self.state.players):
            show_hand = reveal_all or idx == self.human_index
            players.append(
                {
                    "id": idx,
                    "bot": player.bot.name,
                    "placement": player.placement,
                    "hand_size": len(player.hand),
                    "hand": [serialize_card(card) for card in player.hand] if show_hand else [],
                }
            )
        pile_cards = (
            [serialize_card(card) for card in self.state.pile] if reveal_all else []
        )
        return {
            "active_rank": self.state.active_rank,
            "current_player": self.state.current_player,
            "pile": pile_cards,
            "pile_size": len(self.state.pile),
            "placements": list(self.state.placements),
            "known_discarded": dict(self.state.known_discarded),
            "known_revealed": dict(self.state.known_revealed),
            "turn_count": self.state.turn_count,
            "players": players,
        }

    def build_response(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "human_index": self.human_index,
            "public_state": self._public_state(reveal_all=False),
            "debug_state": self._public_state(reveal_all=True),
            "pending_decision": self.pending_decision.to_dict() if self.pending_decision else None,
            "paused": self.paused,
            "finished": self.finished,
            "events": events,
        }

    def _collect_new_events(self, before_idx: int) -> List[Dict[str, Any]]:
        return self.recorder.events[before_idx:]

    def _validate_play(self, player: PlayerState, cards: List[Card]) -> None:
        if not 1 <= len(cards) <= 3:
            raise ValueError("You must select 1-3 cards.")
        for card in cards:
            if card not in player.hand:
                raise ValueError("You must play cards from your hand.")

    def _apply_play(self, player_idx: int, cards: List[Card]) -> None:
        player = self.state.players[player_idx]
        self._validate_play(player, cards)
        if self.state.active_rank is None:
            raise ValueError("Active rank must be set before playing.")
        for card in cards:
            player.hand.remove(card)
            self.state.pile.append(card)
        self.state.turn_count += 1
        self.last_played_cards = list(cards)
        self.last_played_player = player_idx
        self.recorder.record_event(
            "PLAY", player=player_idx, claim_rank=self.state.active_rank, cards=cards
        )
        self.engine._check_wins(self.state, verbose=False)
        self.engine._resolve_discard_quads(self.state, verbose=False)

    def _handle_challenge(self, player_idx: int) -> None:
        next_player = self.engine._next_player(self.active_order, player_idx)
        if next_player is None:
            return
        next_bot = self.state.players[next_player].bot
        public_after_play = PublicState(
            active_rank=self.state.active_rank,
            pile_size=len(self.state.pile),
            hand_sizes=self.state.hand_sizes(),
            known_discarded=self.state.known_discarded.copy(),
            known_revealed=self.state.known_revealed.copy(),
            last_play_count=len(self.last_played_cards),
            last_player_id=player_idx,
        )
        self.state.challenge_stats[next_bot.name]["opportunities"] += 1
        if next_player == self.human_index:
            self.state.current_player = next_player
            self.pending_decision = PendingDecision("CHALLENGE", next_player)
            return
        challenge = next_bot.should_challenge(self.state.players[next_player].hand, public_after_play)
        debug_line = getattr(next_bot, "last_challenge_debug", None)
        if debug_line:
            self.recorder.record_event(
                "CHALLENGE_EVAL", challenger=next_player, message=debug_line
            )
        self.recorder.record_event(
            "CHALLENGE_DECISION", challenger=next_player, challenge=challenge
        )
        if challenge:
            self.state.challenge_stats[next_bot.name]["attempts"] += 1
            truthful = all(card.rank == self.state.active_rank for card in self.last_played_cards)
            if not truthful:
                self.state.challenge_stats[next_bot.name]["success"] += 1
            self.recorder.record_event(
                "CHALLENGE_RESOLUTION",
                challenger=next_player,
                truthful=truthful,
                revealed=self.last_played_cards,
            )
            for card in self.last_played_cards:
                self.state.known_revealed[card.rank] += 1
            picker = next_player if truthful else player_idx
            pickup_size = len(self.state.pile)
            self.state.pile_pickups.append(pickup_size)
            self.recorder.record_event(
                "PICKUP_PILE", player=picker, cards=self.state.pile.copy()
            )
            self.state.players[picker].hand.extend(self.state.pile)
            self.state.pile.clear()
            self.state.active_rank = None
            self.engine._check_wins(self.state, verbose=False)
            self.engine._resolve_discard_quads(self.state, verbose=False)
            next_turn = self.engine._next_player(self.active_order, picker)
            self.state.current_player = next_turn
        else:
            self.state.current_player = next_player
        self.last_played_cards = []
        self.last_played_player = None

    def step(self) -> List[Dict[str, Any]]:
        if self.paused or self.finished:
            return []
        before = len(self.recorder.events)
        while not self.paused and not self.finished:
            if self.pending_decision:
                break
            if not self.active_order:
                self._finalize_if_needed()
                break
            current = self.state.current_player
            if current is None:
                self._finalize_if_needed()
                break
            player = self.state.players[current]
            public = PublicState(
                active_rank=self.state.active_rank,
                pile_size=len(self.state.pile),
                hand_sizes=self.state.hand_sizes(),
                known_discarded=self.state.known_discarded.copy(),
                known_revealed=self.state.known_revealed.copy(),
                last_play_count=0,
                last_player_id=None,
            )
            if self.state.active_rank is None:
                if current == self.human_index:
                    self.pending_decision = PendingDecision("SELECT_RANK", current)
                    break
                chosen = player.bot.choose_active_rank(player.hand, public)
                if chosen not in RANKS:
                    raise ValueError("Bot chose invalid rank")
                self.state.active_rank = chosen
                self.recorder.record_event("SELECT_RANK", player=current, rank=chosen)
            public = PublicState(
                active_rank=self.state.active_rank,
                pile_size=len(self.state.pile),
                hand_sizes=self.state.hand_sizes(),
                known_discarded=self.state.known_discarded.copy(),
                known_revealed=self.state.known_revealed.copy(),
                last_play_count=0,
                last_player_id=None,
            )
            if current == self.human_index:
                self.pending_decision = PendingDecision("PLAY", current)
                break
            played_cards, claim_rank = player.bot.choose_play(player.hand, public)
            if claim_rank != self.state.active_rank:
                raise ValueError("Claimed rank must match active rank")
            self._apply_play(current, played_cards)
            self._handle_challenge(current)
            self._refresh_active_order()
            self._finalize_if_needed()
        return self._collect_new_events(before)

    def apply_action(self, action: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.paused:
            raise ValueError("Game is paused.")
        if self.finished:
            raise ValueError("Game already finished.")
        before = len(self.recorder.events)
        action_type = action.get("type")
        if action_type == "SELECT_RANK":
            if not self.pending_decision or self.pending_decision.decision_type != "SELECT_RANK":
                raise ValueError("Not expecting rank selection right now.")
            rank = action.get("rank")
            if rank not in RANKS:
                raise ValueError("Invalid rank selection.")
            if self.state.active_rank is not None:
                raise ValueError("Active rank already set.")
            self.state.active_rank = rank
            self.recorder.record_event("SELECT_RANK", player=self.pending_decision.player, rank=rank)
            self.pending_decision = PendingDecision("PLAY", self.pending_decision.player)
        elif action_type == "PLAY":
            if not self.pending_decision or self.pending_decision.decision_type != "PLAY":
                raise ValueError("Not expecting a play right now.")
            if self.state.current_player != self.pending_decision.player:
                raise ValueError("It is not your turn.")
            player_idx = self.pending_decision.player
            cards_raw = action.get("cards", [])
            cards = [parse_card(card) for card in cards_raw]
            self._apply_play(player_idx, cards)
            self.pending_decision = None
            self._handle_challenge(player_idx)
            self._refresh_active_order()
            self._finalize_if_needed()
        elif action_type == "CHALLENGE":
            if not self.pending_decision or self.pending_decision.decision_type != "CHALLENGE":
                raise ValueError("Not expecting a challenge decision right now.")
            value = action.get("value")
            if value is None:
                raise ValueError("Challenge decision missing value.")
            challenger = self.pending_decision.player
            self.recorder.record_event(
                "CHALLENGE_DECISION", challenger=challenger, challenge=bool(value)
            )
            self.state.challenge_stats[self.state.players[challenger].bot.name]["attempts"] += (
                1 if value else 0
            )
            if value:
                truthful = all(card.rank == self.state.active_rank for card in self.last_played_cards)
                if not truthful:
                    self.state.challenge_stats[self.state.players[challenger].bot.name]["success"] += 1
                self.recorder.record_event(
                    "CHALLENGE_RESOLUTION",
                    challenger=challenger,
                    truthful=truthful,
                    revealed=self.last_played_cards,
                )
                for card in self.last_played_cards:
                    self.state.known_revealed[card.rank] += 1
                picker = challenger if truthful else self.last_played_player
                if picker is None:
                    raise ValueError("No last player to resolve challenge.")
                pickup_size = len(self.state.pile)
                self.state.pile_pickups.append(pickup_size)
                self.recorder.record_event(
                    "PICKUP_PILE", player=picker, cards=self.state.pile.copy()
                )
                self.state.players[picker].hand.extend(self.state.pile)
                self.state.pile.clear()
                self.state.active_rank = None
                self.engine._check_wins(self.state, verbose=False)
                self.engine._resolve_discard_quads(self.state, verbose=False)
                self.state.current_player = self.engine._next_player(self.active_order, picker)
            else:
                self.state.current_player = challenger
            self.pending_decision = None
            self.last_played_cards = []
            self.last_played_player = None
            self._refresh_active_order()
            self._finalize_if_needed()
        else:
            raise ValueError("Unknown action type.")
        return self._collect_new_events(before)

    def pending_decision_player(self) -> int:
        if not self.pending_decision:
            raise ValueError("No pending decision.")
        return self.pending_decision.player

    def to_save_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "session_id": self.session_id,
            "seed": self.seed,
            "human_index": self.human_index,
            "bot_types": list(self.bot_types),
            "state": _state_to_dict(self.state),
            "active_order": list(self.active_order),
            "pending_decision": self.pending_decision.to_dict() if self.pending_decision else None,
            "last_played_cards": [serialize_card(card) for card in self.last_played_cards],
            "last_played_player": self.last_played_player,
            "bot_rng_states": [
                _jsonify(rng.getstate()) if rng is not None else None for rng in self.bot_rngs
            ],
            "recorder": {
                "metadata": self.recorder.metadata.to_dict(),
                "initial_state": self.recorder.initial_state
                and state_to_dict(self.recorder.initial_state),
                "events": list(self.recorder.events),
                "snapshot_interval": self.recorder.snapshot_interval,
            },
            "paused": self.paused,
            "finished": self.finished,
        }

    @classmethod
    def from_save_dict(cls, data: Dict[str, Any]) -> "GameSession":
        bot_types = list(data["bot_types"])
        session = cls(
            player_count=len(bot_types),
            human_index=data["human_index"],
            bot_types=bot_types,
            seed=data.get("seed"),
        )
        session.session_id = data.get("session_id", session.session_id)
        master_rng_states = data.get("bot_rng_states", [])
        for idx, rng_state in enumerate(master_rng_states):
            if rng_state is None or session.bot_rngs[idx] is None:
                continue
            session.bot_rngs[idx].setstate(_tuplefy(rng_state))
        session.state = _state_from_dict(data["state"], session.engine.players)
        session.active_order = list(data.get("active_order", session.active_order))
        pending = data.get("pending_decision")
        if pending:
            session.pending_decision = PendingDecision(
                pending.get("type"), pending.get("player")
            )
        session.last_played_cards = [
            parse_card(card) for card in data.get("last_played_cards", [])
        ]
        session.last_played_player = data.get("last_played_player")
        session.paused = data.get("paused", False)
        session.finished = data.get("finished", False)
        recorder_data = data.get("recorder", {})
        metadata = recorder_data.get("metadata")
        if metadata:
            session.recorder.metadata.seed = metadata.get("seed")
            session.recorder.metadata.timestamp = metadata.get("timestamp")
            session.recorder.metadata.player_count = metadata.get("player_count")
            session.recorder.metadata.bot_types = list(metadata.get("bot_types", []))
        if recorder_data.get("initial_state"):
            session.recorder.initial_state = state_from_dict(recorder_data.get("initial_state"))
        session.recorder.events = list(recorder_data.get("events", []))
        session.recorder.snapshot_interval = recorder_data.get(
            "snapshot_interval", session.recorder.snapshot_interval
        )
        session._refresh_active_order()
        session._finalize_if_needed()
        return session

    def save_replay(self, replays_dir: str) -> Optional[str]:
        if not self.finished or self.replay_saved:
            return None
        replay = self.recorder.build_replay()
        os.makedirs(replays_dir, exist_ok=True)
        filename = f"interactive_{self.session_id}.json"
        path = os.path.join(replays_dir, filename)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(replay, handle, indent=2, ensure_ascii=False)
        self.replay_saved = True
        return filename
