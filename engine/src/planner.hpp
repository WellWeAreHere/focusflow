#pragma once
#include <vector>

// Picks the set of tasks with the largest total value that fits in the budget (0/1 knapsack).
// minutes[i] and values[i] describe task i. Returns the positions of the chosen tasks.
// Returns an empty list for a budget of 0 or less, or if the two lists differ in length.
std::vector<int> choose(const std::vector<int>& minutes,
                        const std::vector<double>& values,
                        int budget);
