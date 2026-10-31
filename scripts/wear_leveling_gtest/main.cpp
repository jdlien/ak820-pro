#include "gtest/gtest.h"
int main() {
    int f = ::testing::run_all();
    std::printf("%s\n", f ? "RESULT: FAIL" : "RESULT: PASS");
    return f ? 1 : 0;
}
