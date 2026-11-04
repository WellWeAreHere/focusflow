#include "predictors.hpp"

#include <cmath>

using namespace std;

// A sample we can learn from has positive times (otherwise actual / guessed breaks).
static bool usable(const Sample& s) { return s.guessed > 0 && s.actual > 0; }

double predict_raw(double guessed) { return guessed; }

double predict_ratio(const vector<Sample>& history, int category, double guessed) {
    double total = 0;
    int count = 0;
    for (size_t i = 0; i < history.size(); i++) {
        if (history[i].category != category || !usable(history[i])) continue;
        total = total + history[i].actual / history[i].guessed;
        count = count + 1;
    }
    if (count == 0) return guessed;
    return guessed * (total / count);
}

// How different are two tasks? 0 = identical. A different category adds 1,
// and the gap between the logs of the guessed times adds the size difference.
static double distance(int cat_a, double guessed_a, int cat_b, double guessed_b) {
    double d = fabs(log(guessed_a) - log(guessed_b));
    if (cat_a != cat_b) d = d + 1.0;
    return d;
}

double predict_knn(const vector<Sample>& history, int category, double guessed, int k) {
    if (guessed <= 0 || k <= 0) return guessed;

    // Step 1: distance from the new task to every usable past task.
    vector<double> dist;
    vector<double> ratio;
    for (size_t i = 0; i < history.size(); i++) {
        if (!usable(history[i])) continue;
        dist.push_back(distance(category, guessed, history[i].category, history[i].guessed));
        ratio.push_back(history[i].actual / history[i].guessed);
    }
    if (dist.empty()) return guessed;

    // Step 2: pick the k closest, one at a time. Closer neighbours get more weight.
    vector<bool> used(dist.size(), false);
    double weighted_sum = 0;
    double weight_total = 0;
    for (int round = 0; round < k && round < (int)dist.size(); round++) {
        int best = -1;
        for (size_t i = 0; i < dist.size(); i++) {
            if (used[i]) continue;
            if (best == -1 || dist[i] < dist[best]) best = i;
        }
        used[best] = true;
        double weight = 1.0 / (dist[best] + 0.001);
        weighted_sum = weighted_sum + weight * ratio[best];
        weight_total = weight_total + weight;
    }

    // Step 3: the neighbours' average ratio, applied to the new guess.
    return guessed * (weighted_sum / weight_total);
}
