#include "selector.hpp"

#include <cmath>

#include "predictors.hpp"

using namespace std;

vector<Candidate> default_candidates() {
    return {
        {"raw guess", 0, 0},
        {"category ratio", 1, 0},
        {"knn k=1", 2, 1},
        {"knn k=2", 2, 2},
        {"knn k=3", 2, 3},
        {"knn k=5", 2, 5},
    };
}

double predict_with(const Candidate& c, const vector<Sample>& train, int category, double guessed) {
    if (c.model == 0) return predict_raw(guessed);
    if (c.model == 1) return predict_ratio(train, category, guessed);
    return predict_knn(train, category, guessed, c.k);
}

double holdout_error(const Candidate& c, const vector<Sample>& history) {
    size_t split = history.size() * 7 / 10;
    vector<Sample> train(history.begin(), history.begin() + split);

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

Candidate pick_best(const vector<Candidate>& candidates, const vector<Sample>& history, double* error_out) {
    int best = 0;
    double best_error = holdout_error(candidates[0], history);
    for (size_t i = 1; i < candidates.size(); i++) {
        double e = holdout_error(candidates[i], history);
        if (e < best_error) {   // strictly better, so ties keep the simpler model
            best_error = e;
            best = i;
        }
    }
    if (error_out != nullptr) *error_out = best_error;
    return candidates[best];
}
