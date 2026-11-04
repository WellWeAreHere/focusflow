#include <cmath>
#include <cstdio>
#include <vector>

#include "../src/planner.hpp"
#include "../src/predictors.hpp"
#include "../src/selector.hpp"

using namespace std;

static int failures = 0;

static void check(bool ok, const char* what) {
    if (!ok) {
        printf("FAIL: %s\n", what);
        failures = failures + 1;
    }
}

static bool near(double a, double b, double tolerance) { return fabs(a - b) <= tolerance; }

// History in time order. Short coding tasks are accurate, long ones run way over.
static vector<Sample> pattern_history() {
    return {
        {0, 30, 40}, {2, 20, 22},  {1, 60, 60},  {2, 90, 150}, {0, 60, 80},
        {2, 30, 31}, {1, 45, 47},  {2, 100, 170}, {0, 45, 60},  {2, 25, 28},
        {1, 50, 52}, {2, 80, 135}, {0, 20, 27},  {2, 40, 44},  {2, 120, 200},
        {0, 35, 47}, {2, 60, 95},  {1, 30, 31},  {2, 110, 185}, {0, 50, 68},
    };
}

static double total_value(const vector<int>& chosen, const vector<double>& values) {
    double total = 0;
    for (size_t i = 0; i < chosen.size(); i++) total = total + values[chosen[i]];
    return total;
}

static void test_raw_and_ratio() {
    check(predict_raw(45) == 45, "raw returns the guess");

    vector<Sample> h = {{0, 40, 60}, {0, 40, 60}, {0, 40, 60}};
    check(near(predict_ratio(h, 0, 60), 90, 1e-9), "ratio: always 1.5x slower -> 60 becomes 90");
    check(near(predict_ratio(h, 7, 50), 50, 1e-9), "ratio: unseen category returns the guess");
    check(near(predict_ratio({}, 0, 50), 50, 1e-9), "ratio: empty history returns the guess");

    vector<Sample> bad = {{0, 0, 10}, {0, 20, -5}, {0, 40, 60}};
    check(near(predict_ratio(bad, 0, 60), 90, 1e-9), "ratio: ignores rows with non-positive times");
}

static void test_knn() {
    vector<Sample> h = pattern_history();
    check(near(predict_knn(h, 2, 110, 3), 185, 10), "knn: long coding task predicted near 185");
    check(near(predict_knn(h, 2, 35, 3), 37, 5), "knn: short coding task predicted near 37");

    check(near(predict_knn({}, 0, 25, 3), 25, 1e-9), "knn: empty history returns the guess");
    check(near(predict_knn({{0, 30, 45}}, 0, 30, 5), 45, 1e-9), "knn: fewer samples than k still works");
    check(near(predict_knn(h, 0, 0, 3), 0, 1e-9), "knn: a zero guess does not crash");
}

static void test_selector() {
    vector<Sample> h = pattern_history();
    double error = -1;
    Candidate best = pick_best(default_candidates(), h, &error);
    check(best.model == 2, "selector: knn wins on the pattern history");
    check(error >= 0 && error < holdout_error(default_candidates()[0], h), "selector: winner beats raw guess");

    check(holdout_error(default_candidates()[0], {}) > 1e6, "selector: nothing to test on -> huge error");
}

static void test_planner() {
    vector<int> minutes = {1, 2, 3};
    vector<double> values = {6, 10, 12};
    check(near(total_value(choose(minutes, values, 5), values), 22, 1e-9), "planner: best of budget 5 is 22");

    vector<int> m2 = {30, 30, 40};
    vector<double> v2 = {50, 50, 70};
    check(near(total_value(choose(m2, v2, 60), v2), 100, 1e-9), "planner: beats greedy (100, not 70)");

    check(choose(minutes, values, 0).empty(), "planner: zero budget picks nothing");
    check(choose({}, {}, 50).empty(), "planner: no tasks picks nothing");
    check(choose({1, 2}, {5.0}, 10).empty(), "planner: mismatched lists pick nothing");
}

int main() {
    test_raw_and_ratio();
    test_knn();
    test_selector();
    test_planner();
    if (failures == 0) printf("all engine tests passed\n");
    return failures == 0 ? 0 : 1;
}
