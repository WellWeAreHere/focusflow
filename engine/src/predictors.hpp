#pragma once
#include <vector>

#include "types.hpp"

// Each predictor takes a new guess and returns a better estimate of the real minutes.

// 1. Trust the user.
double predict_raw(double guessed);

// 2. Multiply by the average (actual / guessed) of the same category.
double predict_ratio(const std::vector<Sample>& history, int category, double guessed);

// 3. Look at the k most similar past tasks and use their (actual / guessed).
double predict_knn(const std::vector<Sample>& history, int category, double guessed, int k);
