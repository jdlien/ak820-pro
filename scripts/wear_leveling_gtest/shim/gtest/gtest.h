/* A minimal stand-in for googletest: the macros QMK's wear-leveling tests use
 * (quantum/wear_leveling/tests), so they build and run here without the
 * lib/googletest submodule. A failed EXPECT prints and counts; the tests keep
 * running, as gtest's EXPECTs do. scripts/wear_leveling_gtest/run.sh. */
#pragma once
#include <cstdio>
#include <functional>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace testing {
class Test {
   public:
    virtual ~Test() {}
    virtual void SetUp() {}
    virtual void TearDown() {}
    virtual void TestBody() = 0;
};
struct Registered {
    const char*            name;
    std::function<Test*()> make;
};
inline std::vector<Registered>& registry() {
    static std::vector<Registered> r;
    return r;
}
inline int& failures() {
    static int n;
    return n;
}
struct Registrar {
    Registrar(const char* name, std::function<Test*()> make) { registry().push_back({name, make}); }
};
/* Collects a failure's message (the `<<` after an EXPECT) and prints it. */
class Failure {
   public:
    Failure(const char* file, int line, const std::string& what) { s << file << ":" << line << ": " << what; }
    ~Failure() {
        std::cout << "  FAIL " << s.str() << "\n";
        failures()++;
    }
    template <typename T>
    Failure& operator<<(const T& v) {
        s << " " << v;
        return *this;
    }

   private:
    std::ostringstream s;
};
struct Sink {
    template <typename T>
    Sink& operator<<(const T&) {
        return *this;
    }
};
inline int run_all() {
    for (auto& t : registry()) {
        int   before = failures();
        Test* x      = t.make();
        x->SetUp();
        x->TestBody();
        x->TearDown();
        delete x;
        std::cout << (failures() == before ? "ok   " : "FAIL ") << t.name << "\n";
    }
    return failures();
}
} // namespace testing

#define TEST_F(fixture, name)                                                                                                      \
    class fixture##_##name : public fixture {                                                                                      \
       public:                                                                                                                     \
        void TestBody() override;                                                                                                  \
    };                                                                                                                             \
    static ::testing::Registrar reg_##fixture##_##name(#fixture "." #name, [] { return (::testing::Test*)new fixture##_##name; }); \
    void fixture##_##name::TestBody()

#define GT_CHECK(cond, what) \
    if (cond)                \
        ::testing::Sink();   \
    else                     \
        ::testing::Failure(__FILE__, __LINE__, what)
#define EXPECT_TRUE(c) GT_CHECK((c), "EXPECT_TRUE(" #c ")")
#define EXPECT_FALSE(c) GT_CHECK(!(c), "EXPECT_FALSE(" #c ")")
#define EXPECT_EQ(a, b) GT_CHECK((a) == (b), "EXPECT_EQ(" #a ", " #b ")")
#define EXPECT_NE(a, b) GT_CHECK((a) != (b), "EXPECT_NE(" #a ", " #b ")")
