#include <cmath>
#include <cstdio>
#include <vector>

#include "../src/predictors.hpp"

static int failures = 0;
#define CHECK(cond)                                                      \
    do {                                                                 \
        if (!(cond)) {                                                   \
            std::printf("FAIL line %d: %s\n", __LINE__, #cond);          \
            ++failures;                                                  \
        }                                                                \
    } while (0)

// Category 0 always takes 1.5x the guess. Category 1 is always accurate.
static std::vector<ff::Sample> sample_history() {
    std::vector<ff::Sample> h;
    for (int i = 0; i < 10; ++i) {
        h.push_back({0, 40.0, 60.0});
        h.push_back({1, 30.0, 30.0});
    }
    return h;
}

static void test_raw() {
    CHECK(ff::predict_raw({0, 45.0}) == 45.0);
}

static void test_ratio_learns_underestimating() {
    ff::RatioPredictor model;
    model.fit(sample_history());
    double p = model.predict({0, 60.0});
    CHECK(p > 80.0 && p < 90.0);  // pulled towards 90 but shrunk a little
    double q = model.predict({1, 60.0});
    CHECK(q > 60.0 && q < 70.0);  // accurate category stays close to the guess
}

static void test_ratio_unknown_category_and_empty_history() {
    ff::RatioPredictor model;
    CHECK(model.predict({5, 50.0}) == 50.0);  // no data at all: trust the user
    model.fit(sample_history());
    double p = model.predict({99, 100.0});    // unseen category: global average (1.25)
    CHECK(std::fabs(p - 125.0) < 1e-9);
}

int main() {
    test_raw();
    test_ratio_learns_underestimating();
    test_ratio_unknown_category_and_empty_history();
    if (failures == 0) std::printf("all tests passed\n");
    return failures == 0 ? 0 : 1;
}
