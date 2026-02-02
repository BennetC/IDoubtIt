# Lying (Cheat) CLI Simulator

A command-line simulator for the card game **Lying** (a.k.a. Cheat). It supports 2–6 bot players, full turn-by-turn verbose logs, and baseline bot policies for future experimentation.

## Run

```bash
python main.py --players 4 --bots heuristic random heuristic random --games 1 --seed 123 --verbose
```

### CLI Options

- `--players`: number of players (2–6)
- `--bots`: list of bot types per player (repeatable list)
- `--seed`: random seed
- `--games`: number of games to run
- `--verbose`: print full turn-by-turn logs

## Example Logs (trimmed)

### Successful challenge (lie caught)

```
P0(random) plays 1 claiming 2 (pile=1)
Hand sizes -> P0(random):0 P1(heuristic):1
P0(random) finishes in place 1.
P1(heuristic) challenges -> challenge_correct=True (lie)
Revealed: 3♣
P0(random) picks up 1 cards. Pile cleared.
Hand sizes -> P0(random):1 P1(heuristic):1
```

### Failed challenge (truthful play)

```
P0(random) plays 1 claiming 2 (pile=1)
Hand sizes -> P0(random):0 P1(heuristic):1
P0(random) finishes in place 1.
P1(heuristic) challenges -> challenge_correct=False (truthful play)
Revealed: 2♣
P1(heuristic) picks up 1 cards. Pile cleared.
Hand sizes -> P0(random):0 P1(heuristic):2
```

### Pickup → multiple quad discards → instant win

```
P0(random) plays 1 claiming 2 (pile=3)
Hand sizes -> P0(random):5 P1(heuristic):1
P1(heuristic) challenges -> challenge_correct=True (lie)
Revealed: 5♥
P0(random) picks up 3 cards. Pile cleared.
Hand sizes -> P0(random):8 P1(heuristic):1
P0(random) discards four 5s.
Hand sizes -> P0(random):4 P1(heuristic):1
P0(random) discards four 6s.
Hand sizes -> P0(random):0 P1(heuristic):1
P0(random) finishes in place 1.
```

## Tests

```bash
python -m unittest tests/test_rules.py
```
