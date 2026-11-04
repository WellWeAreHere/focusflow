#pragma once

// One finished task from the past. The predictors learn from a list of these.
struct Sample {
    int category;    // 0 = study, 1 = gym, 2 = coding, ...
    double guessed;  // minutes the user thought it would take
    double actual;   // minutes it really took
};
