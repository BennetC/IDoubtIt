from __future__ import annotations

import argparse
import random
from collections import defaultdict
from statistics import mean
from typing import Dict, List

from bots import BOT_TYPES, BotBase
from game import Game


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lying (Cheat) CLI simulator")
    parser.add_argument("--players", type=int, default=4, help="Number of players (2-6)")
    parser.add_argument("--bots", nargs="*", default=None, help="Bot types per player")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--games", type=int, default=1, help="Number of games to run")
    parser.add_argument("--verbose", action="store_true", help="Verbose turn-by-turn log")
    return parser.parse_args()


def build_bots(bot_names: List[str], rng: random.Random) -> List[BotBase]:
    bots: List[BotBase] = []
    for name in bot_names:
        bot_cls = BOT_TYPES.get(name)
        if bot_cls is None:
            raise ValueError(f"Unknown bot type: {name}")
        bots.append(bot_cls(random.Random(rng.randint(0, 1_000_000))))
    return bots


def default_bots(num_players: int) -> List[str]:
    return ["random"] * num_players


def main() -> None:
    args = parse_args()
    if not 2 <= args.players <= 6:
        raise SystemExit("players must be between 2 and 6")
    bot_names = args.bots or default_bots(args.players)
    if len(bot_names) < args.players:
        repeats = (args.players + len(bot_names) - 1) // len(bot_names)
        bot_names = (bot_names * repeats)[: args.players]
    if len(bot_names) != args.players:
        raise SystemExit("Number of bots must match players")

    master_rng = random.Random(args.seed)
    win_counts: Dict[str, int] = defaultdict(int)
    placement_counts: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    game_lengths: List[int] = []
    pickup_sizes: List[int] = []
    challenge_opps: Dict[str, int] = defaultdict(int)
    challenge_attempts: Dict[str, int] = defaultdict(int)
    challenge_success: Dict[str, int] = defaultdict(int)

    for game_idx in range(args.games):
        rng_seed = master_rng.randint(0, 1_000_000)
        bots = build_bots(bot_names, random.Random(rng_seed))
        game = Game(bots, rng_seed=rng_seed)
        state = game.play_game(verbose=args.verbose)
        if args.verbose:
            print(f"=== Game {game_idx + 1} ===")
            for event in state.log:
                print(event.message)
            print("Placements:", state.placements)
        winner = state.placements[0]
        win_counts[state.players[winner].bot.name] += 1
        game_lengths.append(state.turn_count)
        pickup_sizes.extend(state.pile_pickups)
        for idx, placement in enumerate(state.placements, start=1):
            bot_name = state.players[placement].bot.name
            placement_counts[idx][bot_name] += 1
        for bot_name, stats in state.challenge_stats.items():
            challenge_opps[bot_name] += stats["opportunities"]
            challenge_attempts[bot_name] += stats["attempts"]
            challenge_success[bot_name] += stats["success"]

    print("=== Summary ===")
    for bot_name, count in win_counts.items():
        print(f"Wins ({bot_name}): {count}")
    if game_lengths:
        print(f"Average game length (turns): {mean(game_lengths):.2f}")
    if pickup_sizes:
        print(f"Average pile pickup size: {mean(pickup_sizes):.2f}")
    else:
        print("Average pile pickup size: 0.00")
    print("Placement distribution:")
    for place in sorted(placement_counts):
        entries = ", ".join(
            f"{bot_name}: {count}"
            for bot_name, count in placement_counts[place].items()
        )
        print(f"  Place {place}: {entries}")
    print("Challenge rates:")
    for bot_name in sorted(challenge_opps):
        opps = challenge_opps[bot_name]
        attempts = challenge_attempts[bot_name]
        success = challenge_success[bot_name]
        rate = attempts / opps if opps else 0.0
        success_rate = success / attempts if attempts else 0.0
        print(
            f"  {bot_name}: {attempts}/{opps} ({rate:.2%}) challenges,"
            f" success {success_rate:.2%}"
        )


if __name__ == "__main__":
    main()
