from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cards import Card, RANKS


ReplayEvent = Dict[str, Any]


@dataclass
class ReplayMetadata:
    seed: Optional[int]
    timestamp: str
    player_count: int
    bot_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "timestamp": self.timestamp,
            "player_count": self.player_count,
            "bot_types": self.bot_types,
        }


@dataclass
class ReplayPlayerState:
    hand: List[str]
    bot: str
    placement: Optional[int] = None
    discarded: List[str] = field(default_factory=list)


@dataclass
class ReplayState:
    players: List[ReplayPlayerState]
    active_rank: Optional[str]
    pile: List[str]
    current_player: Optional[int]
    placements: List[int]


class ReplayRecorder:
    def __init__(self, metadata: ReplayMetadata, snapshot_interval: int = 10) -> None:
        self.metadata = metadata
        self.snapshot_interval = snapshot_interval
        self.events: List[ReplayEvent] = []
        self.initial_state: Optional[ReplayState] = None

    def set_initial_state(self, state: ReplayState) -> None:
        self.initial_state = state

    def record_event(self, event_type: str, **data: Any) -> None:
        payload: Dict[str, Any] = {"type": event_type}
        for key, value in data.items():
            payload[key] = serialize_value(value)
        self.events.append(payload)

    def build_replay(self) -> Dict[str, Any]:
        if self.initial_state is None:
            raise ValueError("Initial state not set")
        replay = {
            "metadata": self.metadata.to_dict(),
            "initial_state": state_to_dict(self.initial_state),
            "events": self.events,
        }
        if self.snapshot_interval > 0:
            replay["snapshots"] = build_snapshots(replay, self.snapshot_interval)
        return replay


def serialize_card(card: Card) -> str:
    return f"{card.rank}{card.suit}"


def parse_card(value: str) -> Card:
    if len(value) < 2:
        raise ValueError(f"Invalid card value: {value}")
    suit = value[-1]
    rank = value[:-1]
    if rank not in RANKS:
        raise ValueError(f"Invalid card rank: {rank}")
    return Card(rank=rank, suit=suit)


def serialize_value(value: Any) -> Any:
    if isinstance(value, Card):
        return serialize_card(value)
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    return value


def state_to_dict(state: ReplayState) -> Dict[str, Any]:
    return {
        "players": [
            {
                "hand": list(player.hand),
                "bot": player.bot,
                "placement": player.placement,
                "discarded": list(player.discarded),
            }
            for player in state.players
        ],
        "active_rank": state.active_rank,
        "pile": list(state.pile),
        "current_player": state.current_player,
        "placements": list(state.placements),
    }


def state_from_dict(data: Dict[str, Any]) -> ReplayState:
    return ReplayState(
        players=[
            ReplayPlayerState(
                hand=list(player.get("hand", [])),
                bot=player.get("bot", "unknown"),
                placement=player.get("placement"),
                discarded=list(player.get("discarded", [])),
            )
            for player in data["players"]
        ],
        active_rank=data.get("active_rank"),
        pile=list(data.get("pile", [])),
        current_player=data.get("current_player"),
        placements=list(data.get("placements", [])),
    )


def build_initial_state(hands: List[List[Card]], bot_types: List[str]) -> ReplayState:
    players = [
        ReplayPlayerState(hand=[serialize_card(card) for card in hand], bot=bot)
        for hand, bot in zip(hands, bot_types)
    ]
    return ReplayState(
        players=players,
        active_rank=None,
        pile=[],
        current_player=0,
        placements=[],
    )


def reduce_replay(replay: Dict[str, Any], upto_event: Optional[int] = None) -> ReplayState:
    state = state_from_dict(replay["initial_state"])
    events = replay.get("events", [])
    if upto_event is None:
        upto_event = len(events)
    for event in events[:upto_event]:
        apply_event(state, event)
    return state


def apply_event(state: ReplayState, event: Dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "GAME_START":
        return
    if event_type == "SELECT_RANK":
        state.active_rank = event["rank"]
        return
    if event_type == "PLAY":
        player = event["player"]
        cards = event["cards"]
        remove_cards(state.players[player].hand, cards)
        state.pile.extend(cards)
        return
    if event_type == "CHALLENGE_DECISION":
        if not event["challenge"]:
            challenger = event["challenger"]
            state.current_player = challenger
        return
    if event_type == "CHALLENGE_EVAL":
        return
    if event_type == "CHALLENGE_RESOLUTION":
        return
    if event_type == "PICKUP_PILE":
        player = event["player"]
        cards = event["cards"]
        state.players[player].hand.extend(cards)
        state.pile.clear()
        state.active_rank = None
        state.current_player = next_active_player(state, player)
        return
    if event_type == "DISCARD_QUAD":
        player = event["player"]
        cards = event["cards"]
        remove_cards(state.players[player].hand, cards)
        state.players[player].discarded.extend(cards)
        return
    if event_type == "PLACEMENT":
        player = event["player"]
        place = event["place"]
        state.players[player].placement = place
        state.placements.append(player)
        if state.current_player == player:
            state.current_player = next_active_player(state, player)
        return
    if event_type == "GAME_END":
        state.current_player = None
        return
    raise ValueError(f"Unknown event type: {event_type}")


def remove_cards(hand: List[str], cards: List[str]) -> None:
    for card in cards:
        hand.remove(card)


def next_active_player(state: ReplayState, after_player: int) -> Optional[int]:
    active = [idx for idx, player in enumerate(state.players) if player.placement is None]
    if not active:
        return None
    if after_player not in active:
        return active[0]
    idx = active.index(after_player)
    return active[(idx + 1) % len(active)]


def build_snapshots(replay: Dict[str, Any], interval: int) -> List[Dict[str, Any]]:
    state = state_from_dict(replay["initial_state"])
    snapshots: List[Dict[str, Any]] = []
    for idx, event in enumerate(replay.get("events", []), start=1):
        apply_event(state, event)
        if idx % interval == 0:
            snapshots.append({"event_index": idx, "state": state_to_dict(state)})
    return snapshots


def validate_replay(replay: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    try:
        state = state_from_dict(replay["initial_state"])
    except Exception as exc:  # noqa: BLE001
        return [f"Invalid initial state: {exc}"]

    initial_cards: List[str] = []
    for player in state.players:
        initial_cards.extend(player.hand)
    if len(initial_cards) != 52:
        errors.append(f"Initial hands contain {len(initial_cards)} cards (expected 52).")
    if len(set(initial_cards)) != len(initial_cards):
        errors.append("Initial hands contain duplicate cards.")

    events = replay.get("events", [])
    for idx, event in enumerate(events, start=1):
        try:
            apply_event(state, event)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Event {idx} failed to apply: {exc}")
            continue
        errors.extend(validate_state_cards(state, initial_cards, idx))
    return errors


def validate_state_cards(state: ReplayState, initial_cards: List[str], idx: int) -> List[str]:
    errors: List[str] = []
    current_cards: List[str] = []
    for player in state.players:
        current_cards.extend(player.hand)
        current_cards.extend(player.discarded)
    current_cards.extend(state.pile)
    if len(current_cards) != len(initial_cards):
        errors.append(
            f"Event {idx}: card count mismatch ({len(current_cards)} vs {len(initial_cards)})."
        )
    if Counter(current_cards) != Counter(initial_cards):
        errors.append(f"Event {idx}: card conservation violation detected.")
    return errors


def build_metadata(seed: Optional[int], player_count: int, bot_types: List[str]) -> ReplayMetadata:
    timestamp = datetime.now(timezone.utc).isoformat()
    return ReplayMetadata(
        seed=seed,
        timestamp=timestamp,
        player_count=player_count,
        bot_types=bot_types,
    )
