#pragma once
#include <string>
#include <vector>

#include "types.hpp"

// One way of predicting. model: 0 = raw, 1 = ratio, 2 = knn (uses k).
struct Candidate {
    std::string name;
    int model;
    int k;
};

// The list of predictors we compare, simplest first.
std::vector<Candidate> default_candidates();

// Predict minutes with one candidate, learning from `train`.
double predict_with(const Candidate& c, const std::vector<Sample>& train, int category, double guessed);

// Learn from the first 70% of the history, then return the average error (minutes)
// on the last 30%. Returns a huge number if there is nothing to test on.
double holdout_error(const Candidate& c, const std::vector<Sample>& history);

// Returns the candidate with the lowest holdout error (ties keep the simpler one).
// If error_out is not null, it receives that error.
Candidate pick_best(const std::vector<Candidate>& candidates,
                    const std::vector<Sample>& history,
                    double* error_out);
