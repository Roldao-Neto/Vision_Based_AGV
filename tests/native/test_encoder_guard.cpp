// Native tests of sketch/src/encoder_guard, built with the PC's g++ by tests/test_native.py.
#include <cstdio>

#include "encoder_guard/encoder_guard.h"

static int failures;

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            std::printf("%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #cond);                                      \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

static const encoder_guard::Config kConfig = {0.2f, 10};

static void test_trips_after_ticks_without_counts()
{
    encoder_guard::State s;
    encoder_guard::reset(s, 100);
    for (int i = 0; i < 9; i++) {
        CHECK(!encoder_guard::update(s, kConfig, 0.5f, 100));
    }
    CHECK(encoder_guard::update(s, kConfig, 0.5f, 100)); // 10th tick
}

static void test_backward_duty_also_counts_as_driven()
{
    encoder_guard::State s;
    encoder_guard::reset(s, -50);
    bool tripped = false;
    for (int i = 0; i < 10; i++) {
        tripped = encoder_guard::update(s, kConfig, -0.3f, -50);
    }
    CHECK(tripped);
}

static void test_one_count_resets()
{
    encoder_guard::State s;
    encoder_guard::reset(s, 0);
    for (int i = 0; i < 9; i++) {
        encoder_guard::update(s, kConfig, 0.5f, 0);
    }
    CHECK(!encoder_guard::update(s, kConfig, 0.5f, 1)); // moved: back to zero
    for (int i = 0; i < 9; i++) {
        CHECK(!encoder_guard::update(s, kConfig, 0.5f, 1));
    }
    CHECK(encoder_guard::update(s, kConfig, 0.5f, 1));
}

static void test_low_duty_never_trips()
{
    // Below duty_min the wheel may legitimately stand still (start-up, coast, the stop).
    encoder_guard::State s;
    encoder_guard::reset(s, 0);
    for (int i = 0; i < 100; i++) {
        CHECK(!encoder_guard::update(s, kConfig, 0.19f, 0));
        CHECK(!encoder_guard::update(s, kConfig, -0.19f, 0));
    }
}

static void test_low_duty_tick_resets()
{
    encoder_guard::State s;
    encoder_guard::reset(s, 0);
    for (int i = 0; i < 9; i++) {
        encoder_guard::update(s, kConfig, 0.5f, 0);
    }
    CHECK(!encoder_guard::update(s, kConfig, 0.1f, 0));
    CHECK(!encoder_guard::update(s, kConfig, 0.5f, 0));
}

static void test_stays_tripped_until_reset()
{
    encoder_guard::State s;
    encoder_guard::reset(s, 0);
    for (int i = 0; i < 10; i++) {
        encoder_guard::update(s, kConfig, 0.5f, 0);
    }
    CHECK(encoder_guard::update(s, kConfig, 0.0f, 5));
    encoder_guard::reset(s, 5);
    CHECK(!encoder_guard::update(s, kConfig, 0.5f, 5));
}

int main()
{
    test_trips_after_ticks_without_counts();
    test_backward_duty_also_counts_as_driven();
    test_one_count_resets();
    test_low_duty_never_trips();
    test_low_duty_tick_resets();
    test_stays_tripped_until_reset();
    if (failures == 0) {
        std::printf("all encoder_guard tests passed\n");
    }
    return failures == 0 ? 0 : 1;
}
