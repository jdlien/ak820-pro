//! The two ownership wrappers the FFI needs, and property reads.
//!
//! This is the hazard class `macos-port-plan.md:492-497` warns about, kept to
//! one screen: a CF object we own is a [`Cf`], an `io_object_t` we own is an
//! [`Io`], and both release exactly once on drop.

use std::ffi::CString;
use std::os::raw::{c_char, c_void};

use super::sys::*;

/// An owned CoreFoundation reference (the result of a Create or Copy).
pub struct Cf(CFTypeRef);

impl Cf {
    /// Takes ownership of `r`, or `None` for NULL.
    pub fn owned(r: CFTypeRef) -> Option<Cf> {
        (!r.is_null()).then_some(Cf(r))
    }
    pub fn as_ptr(&self) -> CFTypeRef {
        self.0
    }
    pub fn string(s: &str) -> Cf {
        let c = CString::new(s).expect("no interior NUL in a key");
        Cf::owned(unsafe {
            CFStringCreateWithCString(kCFAllocatorDefault, c.as_ptr(), kCFStringEncodingUTF8)
        })
        .expect("CFStringCreateWithCString")
    }
    pub fn to_i64(&self) -> Option<i64> {
        unsafe {
            if CFGetTypeID(self.0) != CFNumberGetTypeID() {
                return None;
            }
            let mut v: i64 = 0;
            (CFNumberGetValue(
                self.0,
                kCFNumberSInt64Type,
                &mut v as *mut i64 as *mut c_void,
            ) != 0)
                .then_some(v)
        }
    }
    pub fn to_string(&self) -> Option<String> {
        unsafe {
            if CFGetTypeID(self.0) != CFStringGetTypeID() {
                return None;
            }
            let mut buf = vec![0 as c_char; 1024];
            if CFStringGetCString(
                self.0,
                buf.as_mut_ptr(),
                buf.len() as CFIndex,
                kCFStringEncodingUTF8,
            ) == 0
            {
                return None;
            }
            Some(
                std::ffi::CStr::from_ptr(buf.as_ptr())
                    .to_string_lossy()
                    .into_owned(),
            )
        }
    }
}

impl Drop for Cf {
    fn drop(&mut self) {
        unsafe { CFRelease(self.0) };
    }
}

/// An owned `io_object_t`.
pub struct Io(pub io_object_t);

impl Drop for Io {
    fn drop(&mut self) {
        if self.0 != 0 {
            unsafe { IOObjectRelease(self.0) };
        }
    }
}

/// A property of `entry` itself. Reading opens nothing.
pub fn property(entry: io_registry_entry_t, key: &str) -> Option<Cf> {
    let k = Cf::string(key);
    Cf::owned(unsafe { IORegistryEntryCreateCFProperty(entry, k.as_ptr(), kCFAllocatorDefault, 0) })
}

/// A property of `entry` or its nearest ancestor that has it.
pub fn inherited(entry: io_registry_entry_t, key: &str) -> Option<Cf> {
    let k = Cf::string(key);
    let plane = c"IOService";
    Cf::owned(unsafe {
        IORegistryEntrySearchCFProperty(
            entry,
            plane.as_ptr(),
            k.as_ptr(),
            kCFAllocatorDefault,
            kIORegistryIterateRecursively | kIORegistryIterateParents,
        )
    })
}
