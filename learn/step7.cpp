 #include <cmath>
#include <iostream>
#include <vector>
using namespace std;

struct Past {
    int category;
    double guessed;
    double actual;
};

// ---------- Predictor 1: trust my guess ----------
double predict_raw(double guessed) {
    return guessed;
}

// ---------- Predictor 2: category ratio (steps 1-3) ----------
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

// ---------- Predictor 3: KNN (new) ----------

// How different are two tasks? 0 = identical. Bigger = less similar.
// - A different category adds 1.
// - A different size adds the gap between their logs. log() makes
//   10 vs 20 minutes count as a big gap, but 110 vs 120 as a small one.
double distance(int cat_a, double guessed_a, int cat_b, double guessed_b) {
    double d = fabs(log(guessed_a) - log(guessed_b));
    if (cat_a != cat_b) d = d + 1.0;
    return d;
}

double predict_knn(const vector<Past>& history, int category, double guessed, int k) {
    if (history.empty()) return guessed;

    // Step 1: how far is the new task from EVERY past task?
    vector<double> dist;
    vector<double> ratio;
    for (size_t i = 0; i < history.size(); i++) {
        dist.push_back(distance(category, guessed, history[i].category, history[i].guessed));
        ratio.push_back(history[i].actual / history[i].guessed);
    }

    // Step 2: pick the k closest, one at a time.
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

        // Step 3: closer neighbours count more.
        double weight = 1.0 / (dist[best] + 0.001);
        weighted_sum = weighted_sum + weight * ratio[best];
        weight_total = weight_total + weight;
    }

    // Step 4: the average ratio of the neighbours, applied to the new guess.
    return guessed * (weighted_sum / weight_total);
}

int main() {
    // 0 = study, 1 = gym, 2 = coding.
    // Pattern hidden in the data: SHORT coding tasks are accurate,
    // LONG coding tasks run way over.
    vector<Past> history = {
        {0, 30, 40}, {0, 60, 80}, {0, 45, 60}, {0, 20, 27},
        {1, 60, 60}, {1, 45, 47}, {1, 50, 52},
        {2, 20, 22}, {2, 30, 31}, {2, 25, 28}, {2, 40, 44},
        {2, 90, 150}, {2, 100, 170}, {2, 80, 135}, {2, 120, 200},
    };

    // Tasks the predictors have NOT seen. We know the real answer, so we can grade them.
    vector<Past> test = {
        {2, 35, 37},
        {2, 110, 185},
        {0, 40, 54},
        {1, 55, 57},
        {2, 95, 160},
    };

    double raw_error = 0;
    double ratio_error = 0;
    double knn_error = 0;

    cout << "guess  real |   raw  ratio    knn" << endl;
    for (size_t i = 0; i < test.size(); i++) {
        double raw = predict_raw(test[i].guessed);
        double rat = predict_ratio(history, test[i].category, test[i].guessed);
        double knn = predict_knn(history, test[i].category, test[i].guessed, 3);

        cout << test[i].guessed << "\t" << test[i].actual << "  |  "
             << (int)(raw + 0.5) << "\t" << (int)(rat + 0.5) << "\t" << (int)(knn + 0.5) << endl;

        // error = how far the prediction is from the truth (always positive)
        raw_error = raw_error + fabs(raw - test[i].actual);
        ratio_error = ratio_error + fabs(rat - test[i].actual);
        knn_error = knn_error + fabs(knn - test[i].actual);
    }

    int n = test.size();
    cout << endl << "average error in minutes (lower is better):" << endl;
    cout << "  raw guess      : " << raw_error / n << endl;
    cout << "  category ratio : " << ratio_error / n << endl;
    cout << "  KNN            : " << knn_error / n << endl;

    return 0;
}
