// Native tests of sketch/src/wheel_pi, built with the PC's g++ by tests/test_native.py.
#include <cmath>
#include <cstdio>

#include "wheel_pi/wheel_pi.h"

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

static const wheel_pi::Config kConfig = {
    {7000.0f, 0.13f, 0.07f}, // fwd
    {6000.0f, 0.15f, 0.09f}, // bwd
    0.1f,                    // t_cl
    0.5f,                    // u_max
    31.0f,                   // v_min
};

static void test_coasts_below_v_min_and_resets()
{
    wheel_pi::State s;
    s.integ = 0.2f;
    CHECK(wheel_pi::update(s, kConfig, 20.0f, 0.0f, 0.0f, 0.02f) == 0.0f);
    CHECK(s.integ == 0.0f);
    CHECK(wheel_pi::update(s, kConfig, -30.0f, 0.0f, 100.0f, 0.02f) == 0.0f);
}

static void test_feedforward_alone_when_tracking()
{
    // v_meas equal to the mean reference: e = 0, u = pwm0 + (v + tau·a)/K.
    wheel_pi::State s;
    s.v_ref_prev = 1000.0f;
    const float u = wheel_pi::update(s, kConfig, 1000.0f, 0.0f, 1000.0f, 0.02f);
    CHECK(near(u, 0.07f + 1000.0f / 7000.0f, 1e-6f));
    CHECK(s.integ == 0.0f);
    s.v_ref_prev = 1000.0f;
    const float ua = wheel_pi::update(s, kConfig, 1000.0f, 3000.0f, 1000.0f, 0.02f);
    CHECK(near(ua, 0.07f + (1000.0f + 0.13f * 3000.0f) / 7000.0f, 1e-6f));
}

static void test_backward_uses_bwd_model_and_sign()
{
    wheel_pi::State s;
    s.v_ref_prev = -1000.0f;
    const float u = wheel_pi::update(s, kConfig, -1000.0f, 0.0f, -1000.0f, 0.02f);
    CHECK(near(u, -0.09f - 1000.0f / 6000.0f, 1e-6f));
}

static void test_pi_gains_and_mean_reference()
{
    // e = (1000 + 900)/2 - 850 = 100 counts/s; Kp = 0.13/(7000·0.1), Ki = 1/(7000·0.1).
    wheel_pi::State s;
    s.v_ref_prev = 900.0f;
    const float u = wheel_pi::update(s, kConfig, 1000.0f, 0.0f, 850.0f, 0.02f);
    const float kp = 0.13f / 700.0f, ki = 1.0f / 700.0f;
    CHECK(near(u, 0.07f + 1000.0f / 7000.0f + kp * 100.0f, 1e-6f));
    CHECK(near(s.integ, ki * 100.0f * 0.02f, 1e-7f));
    CHECK(s.v_ref_prev == 1000.0f);
}

static void test_conditional_integration_at_the_limit()
{
    wheel_pi::State s;
    s.v_ref_prev = 1800.0f;
    s.integ = 0.3f;
    // Clamped at u_max with a positive error: I must not grow.
    CHECK(wheel_pi::update(s, kConfig, 1800.0f, 0.0f, 0.0f, 0.02f) == 0.5f);
    CHECK(s.integ == 0.3f);
    // Clamped but the error pulls u back: I moves (down).
    s.v_ref_prev = 1800.0f;
    s.integ = 0.6f;
    CHECK(wheel_pi::update(s, kConfig, 1800.0f, 0.0f, 2500.0f, 0.02f) == 0.5f);
    CHECK(s.integ < 0.6f);
}

static void test_direction_change_resets_integrator()
{
    wheel_pi::State s;
    s.v_ref_prev = 500.0f;
    s.integ = 0.05f;
    wheel_pi::update(s, kConfig, -500.0f, 0.0f, -500.0f, 0.02f);
    // Reset, then this tick's e = (-500 + 500)/2 - (-500) = 500 adds Ki·e·dt.
    CHECK(near(s.integ, 500.0f * 0.02f / 600.0f, 1e-7f));
}

static void test_closed_loop_settles_on_first_order_plant()
{
    // tau·dv/dt + v = K·(|u| - pwm0), the model the gains were designed for.
    wheel_pi::State s;
    const float dt = 0.02f, h = 0.0005f;
    float v = 0.0f, pos = 0.0f;
    long last = 0;
    float u = 0.0f;
    for (int n = 0; n < 75; n++) {
        const long count = (long)std::floor(pos);
        const float v_meas = (float)(count - last) / dt;
        last = count;
        u = wheel_pi::update(s, kConfig, 622.0f, 0.0f, v_meas, dt); // 0.1 m/s
        const float drive = 7000.0f * std::fmax(std::fabs(u) - 0.07f, 0.0f);
        for (int i = 0; i < 40; i++) {
            v += (drive - v) / 0.13f * h;
            pos += v * h;
        }
    }
    CHECK(near(v, 622.0f, 0.02f * 622.0f));
    CHECK(u < 0.5f);
}

int main()
{
    test_coasts_below_v_min_and_resets();
    test_feedforward_alone_when_tracking();
    test_backward_uses_bwd_model_and_sign();
    test_pi_gains_and_mean_reference();
    test_conditional_integration_at_the_limit();
    test_direction_change_resets_integrator();
    test_closed_loop_settles_on_first_order_plant();
    if (failures == 0) {
        std::printf("all wheel_pi tests passed\n");
    }
    return failures == 0 ? 0 : 1;
}
