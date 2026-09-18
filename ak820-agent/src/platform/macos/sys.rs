//! The IOKit, CoreFoundation and Mach surface this transport uses, declared by
//! hand — the plan's Settled decision, confirmed by spike S2 (37 functions,
//! ownership in two small RAII wrappers; `ak820-agent/spikes/s2-iokit`).
//!
//! Ownership rules, from Apple's "Create/Copy" convention: anything returned by
//! a function with `Create` or `Copy` in its name is ours to `CFRelease`;
//! `Get` returns a borrowed reference. `IOServiceGetMatchingServices` consumes
//! its matching dictionary. `io_object_t` handles are released with
//! `IOObjectRelease`, not `CFRelease`.
#![allow(non_camel_case_types, non_upper_case_globals, dead_code)]

use std::os::raw::{c_char, c_void};

pub type CFTypeRef = *const c_void;
pub type CFAllocatorRef = *const c_void;
pub type CFStringRef = *const c_void;
pub type CFNumberRef = *const c_void;
pub type CFDictionaryRef = *const c_void;
pub type CFMutableDictionaryRef = *mut c_void;
pub type CFRunLoopRef = *mut c_void;
pub type CFRunLoopSourceRef = *mut c_void;
pub type CFIndex = isize;
pub type CFTypeID = usize;
pub type CFTimeInterval = f64;
pub type Boolean = u8;

pub type mach_port_t = u32;
pub type kern_return_t = i32;
pub type io_object_t = mach_port_t;
pub type io_iterator_t = io_object_t;
pub type io_service_t = io_object_t;
pub type io_registry_entry_t = io_object_t;
pub type IOReturn = kern_return_t;
pub type IOOptionBits = u32;
pub type IOHIDDeviceRef = *mut c_void;
pub type IOHIDReportType = u32;

pub const kCFNumberSInt64Type: CFIndex = 4;
pub const kCFStringEncodingUTF8: u32 = 0x0800_0100;

pub const kIORegistryIterateRecursively: IOOptionBits = 1;
pub const kIORegistryIterateParents: IOOptionBits = 2;

pub const kIOHIDOptionsTypeNone: IOOptionBits = 0;
pub const kIOHIDOptionsTypeSeizeDevice: IOOptionBits = 1;
pub const kIOHIDReportTypeOutput: IOHIDReportType = 1;

pub const kIOReturnSuccess: IOReturn = 0;
pub const kIOReturnNoDevice: IOReturn = 0xE00002C0_u32 as i32;
pub const kIOReturnNotPrivileged: IOReturn = 0xE00002C1_u32 as i32;
pub const kIOReturnExclusiveAccess: IOReturn = 0xE00002C5_u32 as i32;
pub const kIOReturnNotOpen: IOReturn = 0xE00002CD_u32 as i32;
pub const kIOReturnTimeout: IOReturn = 0xE00002D6_u32 as i32;
pub const kIOReturnNotPermitted: IOReturn = 0xE00002E2_u32 as i32;
pub const kIOReturnAborted: IOReturn = 0xE00002EB_u32 as i32;
pub const kIOReturnNotResponding: IOReturn = 0xE00002ED_u32 as i32;

pub type IOHIDCallback =
    unsafe extern "C" fn(context: *mut c_void, result: IOReturn, sender: *mut c_void);
pub type IOHIDReportCallback = unsafe extern "C" fn(
    context: *mut c_void,
    result: IOReturn,
    sender: *mut c_void,
    report_type: IOHIDReportType,
    report_id: u32,
    report: *mut u8,
    report_length: CFIndex,
);
pub type IOHIDReportWithTimeStampCallback = unsafe extern "C" fn(
    context: *mut c_void,
    result: IOReturn,
    sender: *mut c_void,
    report_type: IOHIDReportType,
    report_id: u32,
    report: *mut u8,
    report_length: CFIndex,
    time_stamp: u64,
);

#[repr(C)]
pub struct CFRunLoopSourceContext {
    pub version: CFIndex,
    pub info: *mut c_void,
    pub retain: Option<unsafe extern "C" fn(*const c_void) -> *const c_void>,
    pub release: Option<unsafe extern "C" fn(*const c_void)>,
    pub copy_description: Option<unsafe extern "C" fn(*const c_void) -> CFStringRef>,
    pub equal: Option<unsafe extern "C" fn(*const c_void, *const c_void) -> Boolean>,
    pub hash: Option<unsafe extern "C" fn(*const c_void) -> usize>,
    pub schedule: Option<unsafe extern "C" fn(*mut c_void, CFRunLoopRef, CFStringRef)>,
    pub cancel: Option<unsafe extern "C" fn(*mut c_void, CFRunLoopRef, CFStringRef)>,
    pub perform: Option<unsafe extern "C" fn(*mut c_void)>,
}

#[repr(C)]
#[derive(Default)]
pub struct mach_timebase_info_data_t {
    pub numer: u32,
    pub denom: u32,
}

#[link(name = "CoreFoundation", kind = "framework")]
extern "C" {
    pub static kCFAllocatorDefault: CFAllocatorRef;
    pub static kCFRunLoopDefaultMode: CFStringRef;

    pub fn CFRelease(cf: CFTypeRef);
    pub fn CFGetTypeID(cf: CFTypeRef) -> CFTypeID;
    pub fn CFNumberGetTypeID() -> CFTypeID;
    pub fn CFStringGetTypeID() -> CFTypeID;
    pub fn CFNumberGetValue(
        number: CFNumberRef,
        the_type: CFIndex,
        value_ptr: *mut c_void,
    ) -> Boolean;
    pub fn CFStringCreateWithCString(
        alloc: CFAllocatorRef,
        c_str: *const c_char,
        encoding: u32,
    ) -> CFStringRef;
    pub fn CFStringGetCString(
        s: CFStringRef,
        buffer: *mut c_char,
        size: CFIndex,
        encoding: u32,
    ) -> Boolean;

    pub fn CFRunLoopGetCurrent() -> CFRunLoopRef;
    pub fn CFRunLoopRun();
    pub fn CFRunLoopWakeUp(rl: CFRunLoopRef);
    pub fn CFRunLoopSourceCreate(
        alloc: CFAllocatorRef,
        order: CFIndex,
        context: *mut CFRunLoopSourceContext,
    ) -> CFRunLoopSourceRef;
    pub fn CFRunLoopAddSource(rl: CFRunLoopRef, source: CFRunLoopSourceRef, mode: CFStringRef);
    pub fn CFRunLoopSourceSignal(source: CFRunLoopSourceRef);
}

#[link(name = "IOKit", kind = "framework")]
extern "C" {
    pub fn IOServiceMatching(name: *const c_char) -> CFMutableDictionaryRef;
    pub fn IOServiceGetMatchingServices(
        main_port: mach_port_t,
        matching: CFDictionaryRef,
        existing: *mut io_iterator_t,
    ) -> kern_return_t;
    pub fn IOIteratorNext(iterator: io_iterator_t) -> io_object_t;
    pub fn IOObjectRelease(object: io_object_t) -> kern_return_t;
    pub fn IORegistryEntryCreateCFProperty(
        entry: io_registry_entry_t,
        key: CFStringRef,
        allocator: CFAllocatorRef,
        options: IOOptionBits,
    ) -> CFTypeRef;
    pub fn IORegistryEntrySearchCFProperty(
        entry: io_registry_entry_t,
        plane: *const c_char,
        key: CFStringRef,
        allocator: CFAllocatorRef,
        options: IOOptionBits,
    ) -> CFTypeRef;
    pub fn IORegistryEntryGetRegistryEntryID(
        entry: io_registry_entry_t,
        entry_id: *mut u64,
    ) -> kern_return_t;

    pub fn IOHIDDeviceCreate(allocator: CFAllocatorRef, service: io_service_t) -> IOHIDDeviceRef;
    pub fn IOHIDDeviceOpen(device: IOHIDDeviceRef, options: IOOptionBits) -> IOReturn;
    pub fn IOHIDDeviceClose(device: IOHIDDeviceRef, options: IOOptionBits) -> IOReturn;
    pub fn IOHIDDeviceScheduleWithRunLoop(
        device: IOHIDDeviceRef,
        run_loop: CFRunLoopRef,
        mode: CFStringRef,
    );
    pub fn IOHIDDeviceUnscheduleFromRunLoop(
        device: IOHIDDeviceRef,
        run_loop: CFRunLoopRef,
        mode: CFStringRef,
    );
    pub fn IOHIDDeviceRegisterInputReportWithTimeStampCallback(
        device: IOHIDDeviceRef,
        report: *mut u8,
        report_length: CFIndex,
        callback: Option<IOHIDReportWithTimeStampCallback>,
        context: *mut c_void,
    );
    pub fn IOHIDDeviceRegisterRemovalCallback(
        device: IOHIDDeviceRef,
        callback: Option<IOHIDCallback>,
        context: *mut c_void,
    );
    pub fn IOHIDDeviceSetReportWithCallback(
        device: IOHIDDeviceRef,
        report_type: IOHIDReportType,
        report_id: CFIndex,
        report: *const u8,
        report_length: CFIndex,
        timeout: CFTimeInterval,
        callback: Option<IOHIDReportCallback>,
        context: *mut c_void,
    ) -> IOReturn;
}

extern "C" {
    pub static mach_task_self_: mach_port_t;
    pub fn mach_absolute_time() -> u64;
    pub fn mach_timebase_info(info: *mut mach_timebase_info_data_t) -> kern_return_t;
    pub fn mach_port_names(
        task: mach_port_t,
        names: *mut *mut u32,
        names_count: *mut u32,
        types: *mut *mut u32,
        types_count: *mut u32,
    ) -> kern_return_t;
    pub fn vm_deallocate(task: mach_port_t, address: usize, size: usize) -> kern_return_t;
    pub fn proc_pid_rusage(pid: i32, flavor: i32, buffer: *mut c_void) -> i32;
    pub fn getpid() -> i32;
}

// The autorelease pool. ⚠️ Needed because IOKit's HID implementation
// autoreleases into the CALLING thread's pool -- see `cf::Pool`.
#[link(name = "objc")]
extern "C" {
    pub fn objc_autoreleasePoolPush() -> *mut c_void;
    pub fn objc_autoreleasePoolPop(pool: *mut c_void);
}

/// A name for an `IOReturn`, for logs a human reads.
pub fn ioreturn_name(rc: IOReturn) -> String {
    let name = match rc {
        kIOReturnSuccess => "kIOReturnSuccess",
        kIOReturnNoDevice => "kIOReturnNoDevice",
        kIOReturnNotPrivileged => "kIOReturnNotPrivileged",
        kIOReturnExclusiveAccess => "kIOReturnExclusiveAccess",
        kIOReturnNotOpen => "kIOReturnNotOpen",
        kIOReturnTimeout => "kIOReturnTimeout",
        kIOReturnNotPermitted => "kIOReturnNotPermitted",
        kIOReturnAborted => "kIOReturnAborted",
        kIOReturnNotResponding => "kIOReturnNotResponding",
        _ => return format!("IOReturn {:#010X}", rc as u32),
    };
    format!("{name} ({:#010X})", rc as u32)
}

/// Nanoseconds per Mach absolute-time tick (125/3 on Apple Silicon).
pub fn ns_per_tick() -> f64 {
    let mut tb = mach_timebase_info_data_t::default();
    unsafe { mach_timebase_info(&mut tb) };
    tb.numer as f64 / tb.denom as f64
}
