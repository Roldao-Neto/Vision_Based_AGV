#include "samples.h"
#include <Arduino.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include "../config/config.h"
#include "../encoders/encoders.h"

using namespace config;

namespace samples
{   
    constexpr uint32_t kTimerPeriodMs = 2;
    constexpr uint32_t kCapacity = 520 * 3;
    constexpr uint32_t kTicksPerNotification = 2;
    
    static int32_t buffer[kCapacity];
    static volatile uint32_t n_samples; // written by the timer interrupt while it samples
    static uint32_t width;              // values per sample
    static uint32_t max_samples;
    static uint32_t start_us;
    static int32_t start_count[2];
    static struct k_timer timer;
    
    static const char *notify_name;
    static int32_t id;
    static uint32_t per_message;
    static bool sending;
    static uint32_t next_to_send;
    static uint32_t ticks_since_send;
    static atomic_t busy_flag = ATOMIC_INIT(0);
    
    int32_t counts_since_start(int wheel)
    {
        return encoders::count((Wheel)wheel) - start_count[wheel];
    }
    
    uint32_t us_since_start()
    {
        return micros() - start_us;
    }
    
    void add(const int32_t *values)
    {
        const uint32_t n = n_samples;
        if (n >= max_samples) {
            return;
        }
        for (uint32_t i = 0; i < width; i++) {
            buffer[n * width + i] = values[i];
        }
        n_samples = n + 1;
    }
    
    static void add_counts()
    {
        const int32_t values[3] = {
            (int32_t)us_since_start(),
            counts_since_start(kLeft),
            counts_since_start(kRight)
        };
        
        add(values);
    }
    
    // System clock interrupt
    static void on_timer(struct k_timer *)
    {
        add_counts();
    }
    
    void begin()
    {
        k_timer_init(&timer, on_timer, nullptr);
    }
    
    void start(const char *name, int32_t record_id, uint32_t values_per_sample, uint32_t per_notification)
    {
        k_timer_stop(&timer);
        atomic_set(&busy_flag, 1);
        notify_name = name;
        id = record_id;
        width = values_per_sample;
        max_samples = kCapacity / values_per_sample;
        per_message = per_notification;
        sending = false;
        n_samples = 0;
        start_us = micros();
        start_count[kLeft] = encoders::count(kLeft);
        start_count[kRight] = encoders::count(kRight);
    }
    
    void start_count_timer()
    {
        add_counts();
        k_timer_start(&timer, K_MSEC(kTimerPeriodMs), K_MSEC(kTimerPeriodMs));
    }
    
    void stop()
    {
        k_timer_stop(&timer);
        sending = true;
        next_to_send = 0;
        ticks_since_send = kTicksPerNotification; // first notification at the next tick() call, in this same tick
    }
    
    void tick()
    {
        if (!sending || ++ticks_since_send < kTicksPerNotification) {
            return;
        }
        
        ticks_since_send = 0;
        
        const uint32_t total = n_samples;
        const uint32_t first = next_to_send;
        const uint32_t end = min(first + per_message, total);
        
        MsgPack::arr_t<int32_t> flat(buffer + first * width, buffer + end * width);
        
        Bridge.notify(notify_name, id, (int32_t)first, (int32_t)total, flat);

        next_to_send = end;
        
        if (next_to_send >= total) {
            sending = false;
            atomic_set(&busy_flag, 0);
        }
    }
    
    uint32_t count()
    {
        return n_samples;
    }
    
    bool busy()
    {
        return atomic_get(&busy_flag) != 0;
    }
}
