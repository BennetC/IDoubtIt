# Lying (Cheat) CLI Simulator

A command-line simulator for the card game **Lying** (a.k.a. Cheat). It supports 2–6 bot players, full turn-by-turn verbose logs, and baseline bot policies for future experimentation.

## Run

```bash
python main.py --players 4 --bots heuristic random heuristic random --games 1 --seed 123 --verbose
```

### Save a Replay

```bash
python main.py --players 4 --bots heuristic random heuristic random --seed 123 --games 1 --save-replay replays/game_123.json
```

### Run the Replay Web UI

```bash
python webapp.py --replays-dir replays --port 8000
```

Open `http://localhost:8000` in a browser to explore the replay.

### Sample Replay

The repository includes `replays/sample_game_123.json` as a demo replay for the web UI.

### CLI Options

- `--players`: number of players (2–6)
- `--bots`: list of bot types per player (repeatable list)
- `--seed`: random seed
- `--games`: number of games to run
- `--verbose`: print full turn-by-turn logs

## Example Logs (trimmed)

### Successful challenge (lie caught)

```
P0 plays 1 claiming 2 (pile=1)
Hand sizes -> P0:0 P1:1
P0 finishes in place 1.
P1 challenges -> LIE
Revealed: 3♣
P0 picks up 1 cards. Pile cleared.
Hand sizes -> P0:1 P1:1
```

### Failed challenge (truthful play)

```
P0 plays 1 claiming 2 (pile=1)
Hand sizes -> P0:0 P1:1
P0 finishes in place 1.
P1 challenges -> TRUTH
Revealed: 2♣
P1 picks up 1 cards. Pile cleared.
Hand sizes -> P0:0 P1:2
```

### Pickup → multiple quad discards → instant win

```
P0 plays 1 claiming 2 (pile=3)
Hand sizes -> P0:5 P1:1
P1 challenges -> LIE
Revealed: 5♥
P0 picks up 3 cards. Pile cleared.
Hand sizes -> P0:8 P1:1
P0 discards four 5s.
Hand sizes -> P0:4 P1:1
P0 discards four 6s.
Hand sizes -> P0:0 P1:1
P0 finishes in place 1.
```

## Tests

```bash
python -m unittest tests/test_rules.py
```
