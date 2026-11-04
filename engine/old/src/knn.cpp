#include <cmath>

#include "predictors.hpp"

namespace ff {

KnnPredictor::KnnPredictor(int k) : k_(k) {}

void KnnPredictor::fit(const std::vector<Sample>& history) { history_ = history; }

double KnnPredictor::predict(const Query& q) const {
    // TODO (your part): see the hints in the chat.
    return q.estimated;
}

}  // namespace ff
