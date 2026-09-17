// VENDORED into ak820-pro from ~/code/streamdeck-now-playing (MIT, same author),
// src/NowPlaying.Media.Mac/native/nowplaying-mediaremote.m at fc70de4 -- see
// UPSTREAM beside this file for the pin, and scripts/check-helper-upstream.sh
// for drift. ONE local change: `hello` carries "protocol": 1, so the keyboard
// daemon can tell this build from an unversioned one. Fix bugs upstream first
// and re-vendor; do not let the two copies diverge in behaviour.
//
// The MediaRemote helper.
//
// macOS stopped answering MRMediaRemoteGetNowPlayingInfo for ordinary processes
// in 15.4: the callback fires and the dictionary is empty. It still answers an
// Apple platform binary, so this is built as a dylib and loaded into
// /usr/bin/perl, which runs it from a constructor. The plugin never calls
// MediaRemote itself; it supervises this and talks line-JSON over the pipes.
//
// Verified on macOS 26.5.2: the identical code returns 0 keys in our own
// process and full metadata, transport commands and change notifications when
// hosted by perl.
//
// Protocol, one JSON object per line:
//
//   out  {"type":"now", "bundle":..., "title":..., "artist":..., "album":...,
//         "duration":s, "elapsed":s, "rate":n, "artwork":"<sha1>", "stale":bool}
//   out  {"type":"artwork", "key":"<sha1>", "mime":..., "data":"<base64>"}
//   out  {"type":"hello", "pid":n, "protocol":1}   (protocol: the ak820-pro copy only)
//   out  {"type":"tick", "seq":n}
//   in   next | previous | toggle | refresh | artwork <sha1> | quit
//
// "stale" marks a provider that names an owning app but will not say what it is
// playing: the client and playing-state calls answer, the metadata call does
// not. Rather than hang, the helper reports which app owns the session and says
// the metadata is unavailable, and the plugin asks that app directly.
//
// Music.app looked like a permanent instance of this and is not. The metadata
// call was hanging on the deadlock described below, in this process, not in
// MediaRemote: assembling Music's now-playing info decodes its artwork, which
// dlopens an ImageIO codec, which could not run while our constructor held the
// loader lock. With the constructor fixed, Music answers like everything else.
// The flag stays because it is a real state for a provider to be in and because
// asking an app directly is the only thing left if a future macOS closes
// MediaRemote off again.
//
// THE CONSTRUCTOR MUST RETURN. dyld holds its loader lock for the whole of an
// initializer, so anything that keeps this function alive keeps every dlopen in
// the process blocked. An earlier version ran CFRunLoopRun() here, and the
// process deadlocked hard the first time MediaRemote decoded artwork:
//
//   our thread      dlopen -> initializer -> CFRunLoopRun   (holds loader lock)
//   MediaRemote     MRArtwork setImageData -> ImageIO
//                     -> CGImageSourceCopyPropertiesAtIndex
//                     -> IIO_ReaderHandler::buildPluginList -> dlopen  (blocks)
//   our thread      notification -> dispatch_sync onto that same MediaRemote
//                   queue, which is now stuck                       (blocks)
//
// From there every GetNowPlayingInfo and GetPlaybackState piled another blocked
// worker thread onto the same queue until libdispatch's 64-thread soft limit
// stopped the process outright: alive, connected, and permanently silent. So
// there is no run loop here at all. Everything runs on gQueue, the constructor
// returns immediately, and the host process is kept alive by its own script.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <os/lock.h>
#include <CommonCrypto/CommonDigest.h>

typedef void (*MRGetInfo)(dispatch_queue_t, void (^)(NSDictionary *));
typedef void (*MRGetClient)(dispatch_queue_t, void (^)(id));
typedef void (*MRGetIsPlaying)(dispatch_queue_t, void (^)(Boolean));
typedef Boolean (*MRSendCommand)(int, NSDictionary *);
typedef void (*MRRegisterNotifications)(dispatch_queue_t);
typedef CFStringRef (*MRClientBundleID)(id);

static MRGetInfo gGetInfo;
static MRGetClient gGetClient;
static MRGetIsPlaying gGetIsPlaying;
static MRSendCommand gSendCommand;
static MRClientBundleID gClientBundleID;

/// Every MediaRemote call, every notification and every timer runs here. Serial,
/// so one publish at a time, and never the main queue: the host's main thread
/// belongs to perl and is not ours to block.
static dispatch_queue_t gQueue;

static NSString *gArtworkKey;   // sha1 of the artwork last announced
static NSData *gArtworkData;
static NSString *gArtworkMime;
static NSString *gLastLine;     // so unchanged state is not re-sent
static BOOL gPublishQueued;     // coalesces a burst of notifications
static int gTimeouts;           // consecutive calls that never came back
static unsigned long long gTicks;

/// A metadata read that never returns is the Music.app case; bound every call.
static const NSTimeInterval kCallTimeout = 1.5;

/// A timed-out call leaves its worker thread blocked inside MediaRemote for
/// good. Rather than leak them until the process suffocates, give up after a
/// few in a row: the supervisor starts a clean one, which costs a restart and
/// recovers, where the old behaviour cost the media feature until a relaunch.
static const int kMaxTimeouts = 6;

/// Often enough that a stall is caught quickly, rare enough to be free.
static const NSTimeInterval kHeartbeat = 15.0;

/// A slow backstop for players that change without notifying. The Windows build
/// re-syncs every 30 s for the same reason.
static const NSTimeInterval kBackstop = 30.0;

/// stdout is written from gQueue and from the stdin reader thread.
static os_unfair_lock gEmitLock = OS_UNFAIR_LOCK_INIT;

static void emit(NSDictionary *object) {
    NSError *error = nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:object options:0 error:&error];
    if (!json) { return; }
    NSMutableData *line = [json mutableCopy];
    [line appendBytes:"\n" length:1];
    os_unfair_lock_lock(&gEmitLock);
    fwrite(line.bytes, 1, line.length, stdout);
    fflush(stdout);
    os_unfair_lock_unlock(&gEmitLock);
}

static NSString *sha1Hex(NSData *data) {
    unsigned char digest[CC_SHA1_DIGEST_LENGTH];
    CC_SHA1(data.bytes, (CC_LONG)data.length, digest);
    NSMutableString *hex = [NSMutableString stringWithCapacity:CC_SHA1_DIGEST_LENGTH * 2];
    for (int i = 0; i < CC_SHA1_DIGEST_LENGTH; i++) { [hex appendFormat:@"%02x", digest[i]]; }
    return hex;
}

/// Wait out one MediaRemote call. Returns YES if it never answered, and exits
/// the process once too many in a row have not, because they never will.
static BOOL waitBounded(dispatch_semaphore_t done) {
    BOOL timedOut = dispatch_semaphore_wait(
        done, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(kCallTimeout * NSEC_PER_SEC))) != 0;
    if (!timedOut) {
        gTimeouts = 0;
        return NO;
    }

    if (++gTimeouts >= kMaxTimeouts) {
        emit(@{ @"type": @"fatal", @"error": @"MediaRemote stopped answering; restarting" });
        exit(3);
    }
    return YES;
}

/// The bundle id of whatever owns the session. Answers even for Music, which is
/// what lets the plugin route around the metadata call that never returns.
static NSString *currentBundleId(void) {
    if (!gGetClient) { return nil; }
    __block NSString *result = nil;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    gGetClient(dispatch_get_global_queue(0, 0), ^(id client) {
        if (client && gClientBundleID) {
            CFStringRef bundle = gClientBundleID(client);
            if (bundle) { result = [(__bridge NSString *)bundle copy]; }
        }
        dispatch_semaphore_signal(done);
    });
    waitBounded(done);
    return result;
}

static BOOL currentIsPlaying(void) {
    if (!gGetIsPlaying) { return NO; }
    __block BOOL playing = NO;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    gGetIsPlaying(dispatch_get_global_queue(0, 0), ^(Boolean value) {
        playing = value ? YES : NO;
        dispatch_semaphore_signal(done);
    });
    waitBounded(done);
    return playing;
}

static void publish(void) {
    NSString *bundle = currentBundleId();

    __block NSDictionary *info = nil;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    gGetInfo(dispatch_get_global_queue(0, 0), ^(NSDictionary *value) {
        info = [value copy];
        dispatch_semaphore_signal(done);
    });
    BOOL timedOut = waitBounded(done);

    NSMutableDictionary *out = [NSMutableDictionary dictionary];
    out[@"type"] = @"now";
    out[@"bundle"] = bundle ?: [NSNull null];
    // No metadata and something is playing means the provider is refusing to
    // answer for this app, not that nothing is on.
    // The (BOOL) cast matters: without it the expression is an int and
    // NSNumber boxes it as a number, so this arrives as 0/1 rather than
    // false/true and a strict JSON reader rejects the whole message.
    out[@"stale"] = @((BOOL)(timedOut || (info.count == 0 && bundle != nil)));
    out[@"playing"] = @(currentIsPlaying());

    if (info.count > 0) {
        NSString *title = info[@"kMRMediaRemoteNowPlayingInfoTitle"];
        NSString *artist = info[@"kMRMediaRemoteNowPlayingInfoArtist"];
        NSString *album = info[@"kMRMediaRemoteNowPlayingInfoAlbum"];
        if (title) { out[@"title"] = title; }
        if (artist) { out[@"artist"] = artist; }
        if (album) { out[@"album"] = album; }

        NSNumber *duration = info[@"kMRMediaRemoteNowPlayingInfoDuration"];
        NSNumber *elapsed = info[@"kMRMediaRemoteNowPlayingInfoElapsedTime"];
        NSNumber *rate = info[@"kMRMediaRemoteNowPlayingInfoPlaybackRate"];
        if (duration) { out[@"duration"] = duration; }
        if (elapsed) { out[@"elapsed"] = elapsed; }
        if (rate) { out[@"rate"] = rate; }

        // The player's own clock for the elapsed value, so the plugin can
        // extrapolate rather than trust a number that may be seconds old.
        NSDate *stamp = info[@"kMRMediaRemoteNowPlayingInfoTimestamp"];
        if ([stamp isKindOfClass:NSDate.class]) {
            out[@"elapsedAt"] = @([stamp timeIntervalSince1970]);
        }

        NSData *art = info[@"kMRMediaRemoteNowPlayingInfoArtworkData"];
        if ([art isKindOfClass:NSData.class] && art.length > 0) {
            NSString *key = sha1Hex(art);
            out[@"artwork"] = key;
            if (![key isEqualToString:gArtworkKey]) {
                gArtworkKey = key;
                gArtworkData = art;
                gArtworkMime = info[@"kMRMediaRemoteNowPlayingInfoArtworkMIMEType"] ?: @"image/jpeg";
            }
        }
    }

    NSData *encoded = [NSJSONSerialization dataWithJSONObject:out options:NSJSONWritingSortedKeys error:nil];
    NSString *line = [[NSString alloc] initWithData:encoded encoding:NSUTF8StringEncoding];
    if ([line isEqualToString:gLastLine]) { return; }   // nothing moved
    gLastLine = line;
    emit(out);
}

/// Ask for a publish soon. Called from gQueue, including from inside a
/// notification: going through the queue rather than publishing in place keeps
/// MediaRemote's delivery from waiting on our calls back into it, and folds a
/// burst of notifications about one track change into a single publish.
static void schedulePublish(void) {
    if (gPublishQueued) { return; }
    gPublishQueued = YES;
    dispatch_async(gQueue, ^{
        gPublishQueued = NO;
        publish();
    });
}

static void sendArtwork(NSString *key) {
    if (!gArtworkData || ![key isEqualToString:gArtworkKey]) { return; }
    emit(@{
        @"type": @"artwork",
        @"key": gArtworkKey,
        @"mime": gArtworkMime ?: @"image/jpeg",
        @"data": [gArtworkData base64EncodedStringWithOptions:0],
    });
}

/// Commands arrive on stdin, on a thread of their own so a slow publish cannot
/// hold them up. Everything they touch is handed to gQueue.
static void readCommands(void) {
    char buffer[512];
    while (fgets(buffer, sizeof(buffer), stdin)) {
        NSString *line = [[NSString stringWithUTF8String:buffer]
            stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if (line.length == 0) { continue; }

        if ([line isEqualToString:@"quit"]) { exit(0); }
        if ([line isEqualToString:@"refresh"]) {
            dispatch_async(gQueue, ^{ gLastLine = nil; schedulePublish(); });
            continue;
        }
        if ([line hasPrefix:@"artwork "]) {
            NSString *key = [line substringFromIndex:8];
            dispatch_async(gQueue, ^{ sendArtwork(key); });
            continue;
        }

        // MRMediaRemoteCommand: 0 play, 1 pause, 2 toggle, 4 next, 5 previous.
        int command = -1;
        if ([line isEqualToString:@"toggle"]) { command = 2; }
        else if ([line isEqualToString:@"next"]) { command = 4; }
        else if ([line isEqualToString:@"previous"]) { command = 5; }
        if (command >= 0 && gSendCommand) {
            Boolean accepted = gSendCommand(command, nil);
            emit(@{ @"type": @"command", @"name": line, @"accepted": @(accepted ? YES : NO) });
        }
    }
    exit(0);   // the plugin closed the pipe
}

/// A repeating timer on gQueue. Held in a static so ARC cannot release it.
static dispatch_source_t makeTimer(NSTimeInterval interval, dispatch_block_t block) {
    dispatch_source_t timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, gQueue);
    dispatch_source_set_timer(timer, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(interval * NSEC_PER_SEC)),
                              (uint64_t)(interval * NSEC_PER_SEC), NSEC_PER_SEC);
    dispatch_source_set_event_handler(timer, block);
    dispatch_resume(timer);
    return timer;
}

static dispatch_source_t gHeartbeatTimer;
static dispatch_source_t gBackstopTimer;

/// Everything the constructor would have done, run on gQueue so that it happens
/// after dlopen has released the loader lock.
static void setUp(void) {
    void *handle = dlopen("/System/Library/PrivateFrameworks/MediaRemote.framework/MediaRemote", RTLD_NOW);
    if (!handle) {
        emit(@{ @"type": @"fatal", @"error": @"MediaRemote could not be loaded" });
        exit(1);
    }

    gGetInfo = (MRGetInfo)dlsym(handle, "MRMediaRemoteGetNowPlayingInfo");
    gGetClient = (MRGetClient)dlsym(handle, "MRMediaRemoteGetNowPlayingClient");
    gGetIsPlaying = (MRGetIsPlaying)dlsym(handle, "MRMediaRemoteGetNowPlayingApplicationIsPlaying");
    gSendCommand = (MRSendCommand)dlsym(handle, "MRMediaRemoteSendCommand");
    gClientBundleID = (MRClientBundleID)dlsym(handle, "MRNowPlayingClientGetBundleIdentifier");
    MRRegisterNotifications registerFn =
        (MRRegisterNotifications)dlsym(handle, "MRMediaRemoteRegisterForNowPlayingNotifications");

    if (!gGetInfo || !registerFn) {
        emit(@{ @"type": @"fatal", @"error": @"MediaRemote symbols are missing" });
        exit(1);
    }

    // Notifications are posted on gQueue, so the observer blocks run there too
    // and everything stays on one serial queue.
    registerFn(gQueue);
    for (NSString *name in @[@"kMRMediaRemoteNowPlayingInfoDidChangeNotification",
                             @"kMRMediaRemoteNowPlayingApplicationIsPlayingDidChangeNotification",
                             @"kMRNowPlayingPlaybackQueueChangedNotification"]) {
        [NSNotificationCenter.defaultCenter addObserverForName:name object:nil queue:nil
            usingBlock:^(NSNotification *note) { schedulePublish(); }];
    }

    [NSThread detachNewThreadWithBlock:^{ readCommands(); }];

    // Proof that gQueue is still draining. If MediaRemote wedges it -- which is
    // the whole failure this file is arranged around -- the ticks stop and the
    // supervisor restarts the process instead of waiting on a corpse.
    gHeartbeatTimer = makeTimer(kHeartbeat, ^{ emit(@{ @"type": @"tick", @"seq": @(++gTicks) }); });
    gBackstopTimer = makeTimer(kBackstop, ^{ publish(); });

    publish();
}

__attribute__((constructor))
static void start(void) {
    @autoreleasepool {
        emit(@{ @"type": @"hello", @"pid": @(getpid()), @"protocol": @1 });
        gQueue = dispatch_queue_create("com.jdlien.nowplaying.mediaremote", DISPATCH_QUEUE_SERIAL);
        // Async, and then return: see the note at the top of this file. Holding
        // the loader lock any longer than dyld needs deadlocks the process.
        dispatch_async(gQueue, ^{ setUp(); });
    }
}
