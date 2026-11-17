/* Small self-process validation, no Motive/libobs/devices or remote task. */
#import <Foundation/Foundation.h>
#include <assert.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include "../../native/memory-diagnostics.h"

static NSDictionary *sample(void) {
    char *raw = motive_memory_diagnostics();
    assert(raw);
    NSData *data = [NSData dataWithBytes:raw length:strlen(raw)];
    NSDictionary *result = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    free(raw);
    assert(result && [result[@"version"] intValue] == 1);
    assert([result[@"pid"] intValue] == getpid());
    assert([result[@"vm"][@"available"] boolValue]);
    assert(result[@"vm"][@"physical_footprint_bytes"] != [NSNull null]);
    return result;
}

int main(void) {
    @autoreleasepool {
        (void)sample(); // Warm Foundation/JSON before the controlled allocation.
        NSDictionary *before = sample();
        const size_t size = 16 * 1024 * 1024;
        volatile unsigned char *allocation = malloc(size);
        assert(allocation);
        for (size_t index = 0; index < size; index += 4096) allocation[index] = 0x5a;
        NSDictionary *during = sample();
        free((void *)allocation);
        NSDictionary *after = sample();
        long long increase = [during[@"malloc"][@"in_use_bytes"] longLongValue] - [before[@"malloc"][@"in_use_bytes"] longLongValue];
        long long decrease = [during[@"malloc"][@"in_use_bytes"] longLongValue] - [after[@"malloc"][@"in_use_bytes"] longLongValue];
        assert(increase >= (long long)size / 2 && decrease >= (long long)size / 2);
        NSMutableArray *timings = [NSMutableArray array];
        for (int index = 0; index < 30; index++) {
            uint64_t start = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
            NSDictionary *value = sample();
            uint64_t end = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
            [timings addObject:@{@"collection_us": value[@"collection_us"],
                                @"full_call_and_json_parse_us": @((end-start)/1000.0)}];
        }
        NSDictionary *result = @{@"status": @"PASS", @"scope": @"isolated_instrument_selftest_not_Motive_acceptance",
            @"allocated_test_bytes": @(size), @"malloc_in_use_increase": @(increase),
            @"malloc_in_use_decrease_after_free": @(decrease),
            @"before": before, @"during": during, @"after": after, @"timings": timings,
            @"leak_verdict": @"not_evaluated"};
        NSData *json = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
        fwrite(json.bytes, 1, json.length, stdout); fputc('\n', stdout);
    }
    return 0;
}
