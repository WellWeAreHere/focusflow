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

// Category 0 always takes 1.5x the guess, category 1 always matches it.
static std::vector<ff::Sample> history() {
    std::vector<ff::Sample> h;
    for (double est : {20.0, 30.0, 40.0, 50.0, 60.0}) {
        h.push_back({0, est, est * 1.5});
        h.push_back({1, est, est});
    }
    return h;
}

static void test_neighbours_come_from_same_category() {
    ff::KnnPredictor model(3);
    model.fit(history());
    double slow = model.predict({0, 40.0});
    double exact = model.predict({1, 40.0});
    CHECK(slow > 55.0 && slow < 65.0);   // about 60
    CHECK(exact > 38.0 && exact < 42.0); // about 40
}

static void test_edge_cases() {
    ff::KnnPredictor model(5);
    CHECK(model.predict({0, 25.0}) == 25.0);  // no history: trust the user
    model.fit({{0, 30.0, 45.0}});             // fewer samples than k
    double p = model.predict({0, 30.0});
    CHECK(std::fabs(p - 45.0) < 1e-9);
}

int main() {
    test_neighbours_come_from_same_category();
    test_edge_cases();
    if (failures == 0) std::printf("knn: all tests passed\n");
    return failures == 0 ? 0 : 1;
}
