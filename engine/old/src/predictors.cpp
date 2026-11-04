#include "predictors.hpp"

namespace ff {

double predict_raw(const Query& q) { return q.estimated; }

RatioPredictor::RatioPredictor(double prior_strength) : prior_strength_(prior_strength) {}

void RatioPredictor::fit(const std::vector<Sample>& history) {
    by_category_.clear();
    global_ratio_ = 1.0;

    double total = 0.0;
    int n = 0;
    for (const Sample& s : history) {
        if (s.estimated <= 0.0 || s.actual <= 0.0) continue;  // ignore bad rows
        double ratio = s.actual / s.estimated;                // 1.5 means "took 50% longer"
        Stat& stat = by_category_[s.category];
        stat.ratio_sum += ratio;
        stat.count += 1;
        total += ratio;
        n += 1;
    }
    if (n > 0) global_ratio_ = total / n;
}

double RatioPredictor::predict(const Query& q) const {
    double ratio = global_ratio_;  // unknown category falls back to the overall average

    auto it = by_category_.find(q.category);
    if (it != by_category_.end()) {
        // Shrinkage: blend this category's average with the global one.
        // With few samples the global value dominates; with many, the category does.
        const Stat& stat = it->second;
        ratio = (stat.ratio_sum + prior_strength_ * global_ratio_) / (stat.count + prior_strength_);
    }
    return q.estimated * ratio;
}

}  // namespace ff
