#import <Foundation/Foundation.h>
#include <mach/mach.h>
#include <malloc/malloc.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include "memory-diagnostics.h"

static double motive_timeval_seconds(struct timeval value) {
    return (double)value.tv_sec + (double)value.tv_usec / 1000000.0;
}

char *motive_memory_diagnostics(void) {
    @autoreleasepool {
        const uint64_t start = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
        task_vm_info_data_t vm = {0};
        mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
        kern_return_t code = task_info(mach_task_self(), TASK_VM_INFO,
                                      (task_info_t)&vm, &count);
        malloc_statistics_t heap = {0};
        /* Public API sums registered malloc zones. It may briefly take zone
         * locks; this is why collection is explicit and never on media paths. */
        malloc_zone_statistics(NULL, &heap);
        struct rusage usage = {0};
        int usage_result = getrusage(RUSAGE_SELF, &usage);
        int usage_errno = usage_result == 0 ? 0 : errno;
        const uint64_t sampled = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
        BOOL vm_base = code == KERN_SUCCESS && count >= TASK_VM_INFO_REV0_COUNT;
        BOOL footprint = code == KERN_SUCCESS && count >= TASK_VM_INFO_REV1_COUNT;
        id unavailable = [NSNull null];
        NSDictionary *result = @{
            @"version": @1, @"scope": @"current_process_only", @"pid": @(getpid()),
            @"status": footprint && usage_result == 0 ? @"PASS" : @"PARTIAL",
            @"monotonic_ns": @(sampled), @"clock": @"CLOCK_MONOTONIC_RAW",
            @"collection_us": @((sampled - start) / 1000.0),
            @"collection_includes": @"task_info,malloc_zone_statistics,getrusage; excludes JSON serialization and transport",
            @"snapshot_atomic": @NO,
            @"vm": @{
                @"available": @(vm_base), @"kern_return": @(code), @"returned_count": @(count),
                @"physical_footprint_bytes": footprint ? @(vm.phys_footprint) : unavailable,
                @"resident_bytes": vm_base ? @(vm.resident_size) : unavailable,
                @"resident_peak_bytes": vm_base ? @(vm.resident_size_peak) : unavailable,
                @"virtual_bytes": vm_base ? @(vm.virtual_size) : unavailable,
                @"internal_bytes": vm_base ? @(vm.internal) : unavailable,
                @"external_bytes": vm_base ? @(vm.external) : unavailable,
                @"compressed_bytes": vm_base ? @(vm.compressed) : unavailable,
                @"reusable_bytes": vm_base ? @(vm.reusable) : unavailable,
                @"device_bytes": vm_base ? @(vm.device) : unavailable,
                @"region_count": vm_base ? @(vm.region_count) : unavailable,
                @"page_size": vm_base ? @(vm.page_size) : unavailable,
                @"coverage": @"task VM accounting; fields overlap and must not be summed"
            },
            @"malloc": @{
                @"blocks_in_use": @(heap.blocks_in_use),
                @"in_use_bytes": @(heap.size_in_use),
                @"allocated_bytes": @(heap.size_allocated),
                @"zone_high_water_touched_sum_bytes": @(heap.max_size_in_use),
                @"coverage": @"registered malloc zones only; excludes independent mmap, GPU/IOSurface and other allocators",
                @"high_water_semantics": @"sum of zone high-water touched memory; not simultaneous process live-allocation peak"
            },
            @"cpu": @{
                @"available": @(usage_result == 0), @"errno": @(usage_errno),
                @"user_seconds": usage_result == 0 ? @(motive_timeval_seconds(usage.ru_utime)) : unavailable,
                @"system_seconds": usage_result == 0 ? @(motive_timeval_seconds(usage.ru_stime)) : unavailable,
                @"coverage": @"all threads in current process; cumulative CPU, one core equals 100 percent in interval deltas"
            },
            @"limitations": @[@"not a leak diagnosis", @"no allocation stacks or object ownership",
                                @"no memory content or remote task access", @"GPU utilization not measured"]
        };
        NSData *json = [NSJSONSerialization dataWithJSONObject:result options:0 error:nil];
        if (!json) return NULL;
        char *copy = malloc(json.length + 1);
        if (!copy) return NULL;
        memcpy(copy, json.bytes, json.length);
        copy[json.length] = '\0';
        return copy;
    }
}
