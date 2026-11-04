#include <cmath>
#include <iostream>
#include <string>
#include <vector>
using namespace std;

struct Past {
    int category;
    double guessed;
    double actual;
};

struct Todo {
    string name;
    int category;
    int guessed;
    int priority;
    int days_left;
};

// ---------- The three predictors (from step 7) ----------

double predict_raw(double guessed) { return guessed; }

double predict_ratio(const vector<Past>& history, int category, double guessed) {
    double total = 0;
    int count = 0;
    for (size_t i = 0; i < history.size(); i++) {
        if (history[i].category == category) {
            total = total + history[i].actual / history[i].guessed;
            count = count + 1;
        }
    }
    if (count == 0) return guessed;
    return guessed * (total / count);
}

double distance(int cat_a, double guessed_a, int cat_b, double guessed_b) {
    double d = fabs(log(guessed_a) - log(guessed_b));
    if (cat_a != cat_b) d = d + 1.0;
    return d;
}

double predict_knn(const vector<Past>& history, int category, double guessed, int k) {
    if (history.empty()) return guessed;
    vector<double> dist;
    vector<double> ratio;
    for (size_t i = 0; i < history.size(); i++) {
        dist.push_back(distance(category, guessed, history[i].category, history[i].guessed));
        ratio.push_back(history[i].actual / history[i].guessed);
    }
    vector<bool> used(history.size(), false);
    double weighted_sum = 0;
    double weight_total = 0;
    for (int round = 0; round < k && round < (int)history.size(); round++) {
        int best = -1;
        for (size_t i = 0; i < history.size(); i++) {
            if (used[i]) continue;
            if (best == -1 || dist[i] < dist[best]) best = i;
        }
        used[best] = true;
        double weight = 1.0 / (dist[best] + 0.001);
        weighted_sum = weighted_sum + weight * ratio[best];
        weight_total = weight_total + weight;
    }
    return guessed * (weighted_sum / weight_total);
}

// ---------- New: choosing the best predictor automatically ----------

// One way of predicting. model: 0 = raw, 1 = ratio, 2 = knn (uses k).
struct Candidate {
    string name;
    int model;
    int k;
};

double predict_with(const Candidate& c, const vector<Past>& train, int category, double guessed) {
    if (c.model == 0) return predict_raw(guessed);
    if (c.model == 1) return predict_ratio(train, category, guessed);
    return predict_knn(train, category, guessed, c.k);
}

// Learn from the first 70% of the history, then measure the average error
// on the last 30%. Lower is better.
double holdout_error(const Candidate& c, const vector<Past>& history) {
    size_t split = history.size() * 7 / 10;
    vector<Past> train(history.begin(), history.begin() + split);   // the first `split` items

    double total = 0;
    int n = 0;
    for (size_t i = split; i < history.size(); i++) {
        double predicted = predict_with(c, train, history[i].category, history[i].guessed);
        total = total + fabs(predicted - history[i].actual);
        n = n + 1;
    }
    if (n == 0) return 1e9;
    return total / n;
}

// Try every candidate and return the one with the lowest error.
Candidate pick_best(const vector<Candidate>& candidates, const vector<Past>& history) {
    int best = 0;
    double best_error = holdout_error(candidates[0], history);
    cout << "  " << candidates[0].name << ": error " << best_error << endl;
    for (size_t i = 1; i < candidates.size(); i++) {
        double e = holdout_error(candidates[i], history);
        cout << "  " << candidates[i].name << ": error " << e << endl;
        if (e < best_error) {          // strictly better, so ties keep the simpler model
            best_error = e;
            best = i;
        }
    }
    return candidates[best];
}

// ---------- Planner (from step 6) ----------

double value_of(const Todo& t) {
    double urgency = 0;
    if (t.days_left <= 1) urgency = 20;
    else if (t.days_left <= 3) urgency = 10;
    return t.priority * 10 + urgency;
}

vector<int> choose(const vector<int>& minutes, const vector<double>& values, int budget) {
    int n = minutes.size();
    vector<vector<double>> dp(n + 1, vector<double>(budget + 1, 0));
    for (int i = 1; i <= n; i++) {
        for (int t = 0; t <= budget; t++) {
            dp[i][t] = dp[i - 1][t];
            if (minutes[i - 1] <= t) {
                double take = dp[i - 1][t - minutes[i - 1]] + values[i - 1];
                if (take > dp[i][t]) dp[i][t] = take;
            }
        }
    }
    vector<int> chosen;
    int t = budget;
    for (int i = n; i >= 1; i--) {
        if (dp[i][t] != dp[i - 1][t]) {
            chosen.push_back(i - 1);
            t = t - minutes[i - 1];
        }
    }
    return chosen;
}

int main() {
    // History in the order it happened (oldest first). 0 = study, 1 = gym, 2 = coding.
    vector<Past> history = {
        {0, 30, 40}, {2, 20, 22},  {1, 60, 60},  {2, 90, 150}, {0, 60, 80},
        {2, 30, 31}, {1, 45, 47},  {2, 100, 170}, {0, 45, 60},  {2, 25, 28},
        {1, 50, 52}, {2, 80, 135}, {0, 20, 27},  {2, 40, 44},  {2, 120, 200},
        {0, 35, 47}, {2, 60, 95},  {1, 30, 31},  {2, 110, 185}, {0, 50, 68},
    };

    vector<Todo> todos = {
        {"Algo assignment", 0, 60, 4, 1},
        {"Gym",             1, 45, 2, 5},
        {"Build API",       2, 90, 5, 2},
        {"Revise notes",    0, 30, 3, 3},
        {"Fix bug",         2, 40, 3, 7},
    };
    int budget = 180;

    // 1. Let the data decide which predictor to trust.
    vector<Candidate> candidates = {
        {"raw guess", 0, 0}, {"category ratio", 1, 0},
        {"knn k=1", 2, 1}, {"knn k=2", 2, 2}, {"knn k=3", 2, 3}, {"knn k=5", 2, 5},
    };
    cout << "Testing predictors on the most recent tasks:" << endl;
    Candidate best = pick_best(candidates, history);
    cout << "Winner: " << best.name << endl << endl;

    // 2. Predict minutes for today's tasks using the winner (trained on ALL history now).
    vector<int> minutes;
    vector<double> values;
    for (size_t i = 0; i < todos.size(); i++) {
        double m = predict_with(best, history, todos[i].category, todos[i].guessed);
        minutes.push_back((int)(m + 0.5));
        values.push_back(value_of(todos[i]));
    }

    // 3. Plan.
    vector<int> chosen = choose(minutes, values, budget);
    cout << "Plan for " << budget << " minutes:" << endl;
    int total = 0;
    for (size_t k = 0; k < chosen.size(); k++) {
        int i = chosen[k];
        cout << "  " << todos[i].name << "  (guessed " << todos[i].guessed
             << ", expected " << minutes[i] << " min)" << endl;
        total = total + minutes[i];
    }
    cout << "  total expected = " << total << " min" << endl;

    return 0;
}
