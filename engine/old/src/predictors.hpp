#pragma once
#include <unordered_map>
#include <vector>

namespace ff {

// One finished piece of work from the user's history.
struct Sample {
    int category;      // id of the category ("Study" = 0, "Coding" = 1, ...)
    double estimated;  // minutes the user GUESSED
    double actual;     // minutes it REALLY took
};

// A new task we want a duration prediction for.
struct Query {
    int category;
    double estimated;
};

// Predictor 1: trust the user. This is the baseline every other model must beat.
double predict_raw(const Query& q);

// Predictor 2: "you usually take X times longer than you guess in this category".
class RatioPredictor {
public:
    // prior_strength = how many "pretend" samples we add at the global average.
    // Bigger = slower to trust a category's own data.
    explicit RatioPredictor(double prior_strength = 3.0);

    void fit(const std::vector<Sample>& history);
    double predict(const Query& q) const;

private:
    struct Stat {
        double ratio_sum = 0.0;
        int count = 0;
    };
    double prior_strength_;
    double global_ratio_ = 1.0;
    std::unordered_map<int, Stat> by_category_;
};

// Predictor 3: "find similar past tasks and look at what happened to them".
class KnnPredictor {
public:
    explicit KnnPredictor(int k = 5);

    void fit(const std::vector<Sample>& history);
    double predict(const Query& q) const;

private:
    int k_;
    std::vector<Sample> history_;
};

}  // namespace ff
