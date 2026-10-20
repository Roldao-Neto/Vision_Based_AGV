// Native tests of sketch/src/heading_pi, built with the PC's g++ by tests/test_native.py.
#include <cmath>
#include <cstdio>

#include "heading_pi/heading_pi.h"

static int failures;

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            std::printf("%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #cond);                                      \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

static bool near(float a, float b, float tol)
{
    return std::fabs(a - b) <= tol;
}

static const heading_pi::Config kConfig = {2.0f, 1.0f, 0.0f, 0.5f};

static void test_wrap()
{
    CHECK(near(heading_pi::wrap(0.1f), 0.1f, 1e-6f));
    CHECK(near(heading_pi::wrap(3.3f), 3.3f - 6.2831853f, 1e-5f));
    CHECK(near(heading_pi::wrap(-3.3f), -3.3f + 6.2831853f, 1e-5f));
    CHECK(near(heading_pi::wrap(4.0f * 3.1415927f + 0.2f), 0.2f, 1e-5f));
    CHECK(heading_pi::wrap(3.1415927f) > 0.0f); // (−π, π]
}

static void test_proportional_and_integral()
{
    heading_pi::State s;
    const float w = heading_pi::update(s, kConfig, 0.05f, 0.02f);
    CHECK(near(w, 2.0f * 0.05f, 1e-7f));
    CHECK(near(s.integ, 2.0f / 1.0f * 0.05f * 0.02f, 1e-8f));
    // Sign: a positive error (target counter-clockwise of θ) turns counter-clockwise.
    CHECK(w > 0.0f);
}

static void test_clamp_and_conditional_integration()
{
    heading_pi::State s;
    s.integ = 0.1f;
    CHECK(heading_pi::update(s, kConfig, 0.5f, 0.02f) == 0.5f);
    CHECK(s.integ == 0.1f); // clamped and pushing further: no integration
    s.integ = 0.6f;
    CHECK(heading_pi::update(s, kConfig, -0.01f, 0.02f) == 0.5f);
    CHECK(s.integ < 0.6f); // clamped, but the error pulls back: integrates
}

static void test_removes_a_constant_bias()
{
    // The wheels turn the robot by a constant 0.05 rad/s on their own (e.g. different wheel
    // diameters); θ' = ω_cmd + bias, with the wheel loops as a 0.1 s first-order lag. The
    // integral must bring the heading back to the target.
    heading_pi::State s;
    float th = 0.0f, w_act = 0.0f;
    const float dt = 0.02f, bias = 0.05f;
    for (int i = 0; i < 500; i++) {
        const float w_cmd = heading_pi::update(s, kConfig, heading_pi::wrap(0.0f - th), dt);
        w_act += (w_cmd - w_act) * dt / 0.1f;
        th += (w_act + bias) * dt;
    }
    CHECK(std::fabs(th) < 1e-3f);
    CHECK(near(s.integ, -bias, 2e-3f));
}

int main()
{
    test_wrap();
    test_proportional_and_integral();
    test_clamp_and_conditional_integration();
    test_removes_a_constant_bias();
    if (failures == 0) {
        std::printf("all heading_pi tests passed\n");
    }
    return failures == 0 ? 0 : 1;
}
