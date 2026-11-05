# Simulation results

All numbers come from **simulated** users (fixed random seeds, so the run is repeatable). The patterns are my assumptions, not measurements of real people:

- study tasks really take 1.4x the guess; gym 0.95x; chores 0.8x;
- coding tasks guessed at 30 min or less take 1.05x, at 90 min or more 1.7x (in between: a straight line);
- each user scales those ratios by a random 0.85-1.15, and every task has +/-15% random wobble;
- the "calibrated" group guesses perfectly on average (ratio 1.0): a check that FocusFlow does no harm.

The coding pattern (size matters) is one the KNN predictor is built to catch, so the simulation favours it. Treat the size of the gain as 'what is possible when such a pattern exists'.

## Users who misjudge their time

**Prediction error** (average minutes off, on 100 unseen tasks per user, 30 users)

| Sessions of history | Your own guess | FocusFlow | Improvement |
|---|---|---|---|
| 5 (too few: uses category ratio) | 27.2 min | 16.4 min | 40% |
| 10 | 27.2 min | 17.4 min | 36% |
| 20 | 27.2 min | 14.8 min | 46% |
| 40 | 27.2 min | 13.5 min | 50% |
| 80 | 27.2 min | 13.0 min | 52% |
| 160 | 27.2 min | 12.8 min | 53% |

**Predictor chosen by the selector** (at 160 sessions of history)

- knn k=5: 12 of 30 users
- category ratio: 11 of 30 users
- knn k=2: 3 of 30 users
- knn k=1: 3 of 30 users
- knn k=3: 1 of 30 users

**Plans** (200 random situations per user, 8 tasks, time for about half of them; 30 users)

| Plan built from | Value actually completed | Share of the best possible | Plan overran the time |
|---|---|---|---|
| your own guesses | 170.5 | 87% | 76% of the time |
| FocusFlow predictions | 184.5 | 94% | 23% of the time |
| the real times (impossible in practice) | 195.9 | 100% | 0% of the time |

## Control: users whose guesses are already accurate

**Prediction error** (average minutes off, on 100 unseen tasks per user, 30 users)

| Sessions of history | Your own guess | FocusFlow | Improvement |
|---|---|---|---|
| 5 (too few: uses category ratio) | 7.9 min | 9.5 min | -20% |
| 10 | 7.9 min | 9.8 min | -23% |
| 20 | 7.9 min | 8.8 min | -11% |
| 40 | 7.9 min | 8.3 min | -5% |
| 80 | 7.9 min | 8.4 min | -5% |
| 160 | 7.9 min | 7.9 min | -0% |

**Predictor chosen by the selector** (at 160 sessions of history)

- raw guess: 22 of 30 users
- category ratio: 8 of 30 users

**Plans** (200 random situations per user, 8 tasks, time for about half of them; 30 users)

| Plan built from | Value actually completed | Share of the best possible | Plan overran the time |
|---|---|---|---|
| your own guesses | 203.5 | 96% | 30% of the time |
| FocusFlow predictions | 203.6 | 96% | 29% of the time |
| the real times (impossible in practice) | 213.0 | 100% | 0% of the time |

