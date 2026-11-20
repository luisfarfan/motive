// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>
@protocol H22Probe
- (void)probe:(NSFileHandle*)capability reply:(void (^)(NSDictionary*))reply;
@end
