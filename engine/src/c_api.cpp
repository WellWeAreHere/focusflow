// The "bridge": plain functions that Python (through ctypes) can call.
// Python can't pass a C++ vector or string, so everything here is flat arrays and numbers.
#include <cstdio>
#include <vector>

#include "planner.hpp"
#include "predictors.hpp"
#include "selector.hpp"
#include "types.hpp"

#ifdef _WIN32
#define FF_EXPORT extern "C" __declspec(dllexport)
#else
#define FF_EXPORT extern "C"
#endif

using namespace std;

// With fewer past tasks than this, grading predictors on a held-out part is meaningless.
static const int MIN_HISTORY_TO_COMPARE = 10;

// Learns from the history and predicts real minutes for each new task.
//   history: n_hist past tasks (category, guessed, actual), oldest first.
//   tasks:   n_tasks new tasks (category, guessed).
//   out_minutes: room for n_tasks numbers, filled with the predictions.
//   out_model: room for out_model_len characters, filled with the winning predictor's name.
//   out_error: receives the winner's average error in minutes (-1 if it wasn't tested).
// Returns 0 on success, -1 on invalid arguments.
FF_EXPORT int ff_predict(const int* hist_cat, const double* hist_guessed, const double* hist_actual, int n_hist,
                         const int* task_cat, const double* task_guessed, int n_tasks,
                         double* out_minutes, char* out_model, int out_model_len, double* out_error) {
    if (n_hist < 0 || n_tasks < 0 || out_minutes == nullptr || out_model == nullptr || out_model_len <= 0) return -1;
    if ((n_hist > 0 && (hist_cat == nullptr || hist_guessed == nullptr || hist_actual == nullptr)) ||
        (n_tasks > 0 && (task_cat == nullptr || task_guessed == nullptr))) return -1;

    vector<Sample> history;
    for (int i = 0; i < n_hist; i++) history.push_back({hist_cat[i], hist_guessed[i], hist_actual[i]});

    Candidate winner = {"category ratio (history too small to compare)", 1, 0};
    double error = -1;
    if (n_hist >= MIN_HISTORY_TO_COMPARE) winner = pick_best(default_candidates(), history, &error);

    for (int i = 0; i < n_tasks; i++) {
        out_minutes[i] = predict_with(winner, history, task_cat[i], task_guessed[i]);
    }
    snprintf(out_model, out_model_len, "%s", winner.name.c_str());
    if (out_error != nullptr) *out_error = error;
    return 0;
}

// Picks the best set of tasks for the budget.
//   minutes/values: n numbers each. out_chosen: room for n ints.
// Returns how many tasks were chosen (their positions are written to out_chosen), or -1 on bad arguments.
FF_EXPORT int ff_plan(const int* minutes, const double* values, int n, int budget, int* out_chosen) {
    if (n < 0 || (n > 0 && (minutes == nullptr || values == nullptr || out_chosen == nullptr))) return -1;

    vector<int> m(minutes, minutes + n);
    vector<double> v(values, values + n);
    vector<int> chosen = choose(m, v, budget);

    for (size_t i = 0; i < chosen.size(); i++) out_chosen[i] = chosen[i];
    return (int)chosen.size();
}
