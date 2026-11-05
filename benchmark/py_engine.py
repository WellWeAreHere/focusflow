# The same engine as engine/src/*.cpp, written in plain Python, line for line.
# It exists only to answer one question fairly: "how much faster is the C++ version?"
# For that to mean anything the two must compute the SAME answers, so test_equivalence.py checks it.
#
# Samples are tuples (category, guessed, actual), the same data as the C++ `Sample` struct.
import math

MIN_HISTORY_TO_COMPARE = 10   # same rule as c_api.cpp

# (name, model, k) with model 0 = raw guess, 1 = category ratio, 2 = knn. Same list and order as C++.
CANDIDATES = [
    ("raw guess", 0, 0),
    ("category ratio", 1, 0),
    ("knn k=1", 2, 1),
    ("knn k=2", 2, 2),
    ("knn k=3", 2, 3),
    ("knn k=5", 2, 5),
]


def usable(sample):
    return sample[1] > 0 and sample[2] > 0


def predict_raw(guessed):
    return guessed


def predict_ratio(history, category, guessed):
    total = 0.0
    count = 0
    for s in history:
        if s[0] != category or not usable(s):
            continue
        total = total + s[2] / s[1]
        count = count + 1
    if count == 0:
        return guessed
    return guessed * (total / count)


def distance(cat_a, guessed_a, cat_b, guessed_b):
    d = abs(math.log(guessed_a) - math.log(guessed_b))
    if cat_a != cat_b:
        d = d + 1.0
    return d


def predict_knn(history, category, guessed, k):
    if guessed <= 0 or k <= 0:
        return guessed

    dist = []
    ratio = []
    for s in history:
        if not usable(s):
            continue
        dist.append(distance(category, guessed, s[0], s[1]))
        ratio.append(s[2] / s[1])
    if not dist:
        return guessed

    used = [False] * len(dist)
    weighted_sum = 0.0
    weight_total = 0.0
    for _ in range(min(k, len(dist))):
        best = -1
        for i in range(len(dist)):
            if used[i]:
                continue
            if best == -1 or dist[i] < dist[best]:
                best = i
        used[best] = True
        weight = 1.0 / (dist[best] + 0.001)
        weighted_sum = weighted_sum + weight * ratio[best]
        weight_total = weight_total + weight

    return guessed * (weighted_sum / weight_total)


def predict_with(candidate, train, category, guessed):
    model = candidate[1]
    if model == 0:
        return predict_raw(guessed)
    if model == 1:
        return predict_ratio(train, category, guessed)
    return predict_knn(train, category, guessed, candidate[2])


def holdout_error(candidate, history):
    split = len(history) * 7 // 10
    train = history[:split]
    total = 0.0
    n = 0
    for s in history[split:]:
        predicted = predict_with(candidate, train, s[0], s[1])
        total = total + abs(predicted - s[2])
        n = n + 1
    if n == 0:
        return 1e9
    return total / n


def pick_best(history):
    best = 0
    best_error = holdout_error(CANDIDATES[0], history)
    for i in range(1, len(CANDIDATES)):
        e = holdout_error(CANDIDATES[i], history)
        if e < best_error:
            best_error = e
            best = i
    return CANDIDATES[best], best_error


def predict_minutes(history, tasks):
    """Same contract as backend/engine.py: returns (minutes_list, model_name, avg_error_or_None)."""
    winner = ("category ratio (history too small to compare)", 1, 0)
    error = None
    if len(history) >= MIN_HISTORY_TO_COMPARE:
        winner, error = pick_best(history)
    minutes = [predict_with(winner, history, cat, guessed) for cat, guessed in tasks]
    return minutes, winner[0], error


def make_plan(minutes, values, budget):
    """0/1 knapsack with a full table, same as planner.cpp. Returns chosen positions, last task first."""
    chosen = []
    if budget <= 0 or len(minutes) != len(values):
        return chosen
    if any(m < 0 for m in minutes):
        return chosen
    n = len(minutes)

    dp = [[0.0] * (budget + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for t in range(budget + 1):
            dp[i][t] = dp[i - 1][t]
            if minutes[i - 1] <= t:
                take = dp[i - 1][t - minutes[i - 1]] + values[i - 1]
                if take > dp[i][t]:
                    dp[i][t] = take

    t = budget
    for i in range(n, 0, -1):
        if dp[i][t] != dp[i - 1][t]:
            chosen.append(i - 1)
            t = t - minutes[i - 1]
    return chosen
