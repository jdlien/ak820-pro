// AK820 F19 Listener: the Mac's end of the wake rig (plans/POWER-CAMPAIGN-PLAN.md,
// R7; history/wake-rig-2026-10-16/). The rig's relay presses F19; this records
// when each F19 down and up reached the Mac, so a test can count drops and time
// latency against the press, both on this Mac's clock.
//
// ⚠️ It sees every key event (an event tap needs Input Monitoring), so it is
// written not to be a keylogger: F19 and F20 are matched inside the callback
// and every other event is returned untouched, never stored, never written.
//
// Since 11-03 it also swallows F19 and F20 once logged, so the presser's
// batches reach no app (a 12:54 batch's ~1,900 presses beeped and drove Xcode
// on the Mac in use). Dropping an event takes an active tap, which needs
// Accessibility as well; without that grant it asks for it once and listens
// only, as before, and says so in the log.
//
// One line per F19 or F20 event, appended to ~/Library/Logs/ak820pro/f19.log:
//   <unix time of the event, s> <down|up> <event timestamp, ns since boot>
//   <unix time of the event, s> <f20-down|f20-up> <event timestamp, ns since boot>
// F20 (11-03) is the presser's second channel, (3,14). Its own token keeps
// it out of every parser that takes field 2 as "down" or "up" for F19.
// The unix time is the event's own timestamp mapped onto the wall clock (the
// callback's lag does not count). Started by `open` (so TCC sees this app, not
// whatever shell started it); built and signed by scripts/build-f19-listener.sh.
import ApplicationServices
import CoreGraphics
import Foundation
import IOKit.hid

// Static members, not top-level variables: a C callback cannot capture
// context, and main.swift's top-level variables count as context.
enum Rig {
    static let f19: Int64 = 0x50   // kVK_F19
    static let f20: Int64 = 0x5A   // kVK_F20
    static var tap: CFMachPort?
    static var swallow = false   // an active tap: F19/F20 dropped after logging
    static let out: FileHandle = {
        let dir = (NSHomeDirectory() as NSString).appendingPathComponent("Library/Logs/ak820pro")
        let path = (dir as NSString).appendingPathComponent("f19.log")
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: path) {
            FileManager.default.createFile(atPath: path, contents: nil)
        }
        guard let h = FileHandle(forWritingAtPath: path) else { exit(1) }
        h.seekToEndOfFile()
        return h
    }()

    static func note(_ s: String) {
        out.write((s + "\n").data(using: .utf8)!)
    }

    // The event's timestamp is nanoseconds since boot on the uptime clock that
    // does not count sleep; map it onto the wall clock through one reading of both.
    static func wallTime(ofEventNs ns: UInt64) -> Double {
        let upNow = clock_gettime_nsec_np(CLOCK_UPTIME_RAW)
        let wallNow = Date().timeIntervalSince1970
        return wallNow - (Double(upNow) - Double(ns)) / 1e9
    }
}

if IOHIDCheckAccess(kIOHIDRequestTypeListenEvent) != kIOHIDAccessTypeGranted {
    _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
    Rig.note(String(format: "%.6f note no Input Monitoring yet: grant it to AK820 F19 Listener, then start it again",
                Date().timeIntervalSince1970))
    exit(2)
}

let mask = (1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.keyUp.rawValue)
let callback: CGEventTapCallBack = { _, type, event, _ in
    // macOS switches a tap off if a callback ever runs slow; switch it back on,
    // and say so, since presses in the gap were missed by us, not the board.
    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        if let t = Rig.tap { CGEvent.tapEnable(tap: t, enable: true) }
        Rig.note(String(format: "%.6f note the tap was disabled (%d) and re-enabled",
                        Date().timeIntervalSince1970, type.rawValue))
        return Unmanaged.passUnretained(event)
    }
    let code = event.getIntegerValueField(.keyboardEventKeycode)
    if (type == .keyDown || type == .keyUp) && (code == Rig.f19 || code == Rig.f20) {
        let ts = event.timestamp
        let edge = type == .keyDown ? "down" : "up"
        Rig.note(String(format: "%.6f %@ %llu", Rig.wallTime(ofEventNs: ts),
                    code == Rig.f19 ? edge : "f20-" + edge, ts))
        if Rig.swallow { return nil }
    }
    return Unmanaged.passUnretained(event)
}
let trusted = AXIsProcessTrustedWithOptions(
    [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary)
var made: CFMachPort? = nil
if trusted {
    made = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap,
                             options: .defaultTap, eventsOfInterest: CGEventMask(mask),
                             callback: callback, userInfo: nil)
    Rig.swallow = made != nil
}
if made == nil {
    Rig.note(String(format: "%.6f note no Accessibility%@: listening only, so F19/F20 also reach the apps",
                    Date().timeIntervalSince1970, trusted ? " tap" : " yet (grant it, then start this again)"))
    made = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap,
                             options: .listenOnly, eventsOfInterest: CGEventMask(mask),
                             callback: callback, userInfo: nil)
}
guard let tap = made else {
    Rig.note(String(format: "%.6f note the event tap could not be created", Date().timeIntervalSince1970))
    exit(3)
}
Rig.tap = tap
let src = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
CFRunLoopAddSource(CFRunLoopGetCurrent(), src, .commonModes)
CGEvent.tapEnable(tap: tap, enable: true)
Rig.note(String(format: "%.6f note listening (pid %d)%@", Date().timeIntervalSince1970, getpid(),
                Rig.swallow ? ", F19/F20 swallowed" : ""))
CFRunLoopRun()
