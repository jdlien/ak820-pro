//! Which HID service is the board's raw-HID interface — decided from
//! IORegistry properties, with **nothing opened**.
//!
//! G-A, restated for macOS: the decision of which device to open is made from
//! properties read without opening. On Windows that is
//! `CM_Get_Device_Interface_ListW`. Here it is `IOServiceGetMatchingServices`
//! plus property reads.
//!
//! ⚠️ **Never `IOHIDManagerOpen`.** Apple documents it as opening every device
//! the manager matched, current and future, which is macOS's `hid_enumerate`
//! trap. Nothing in this file creates a manager.

use super::cf::{inherited, property, Cf, Io};
use super::sys::*;

const VID: i64 = crate::hid::VID as i64;
const PID: i64 = crate::hid::PID as i64;
const RAW_USAGE_PAGE: i64 = crate::hid::USAGE_PAGE as i64;
const RAW_USAGE: i64 = crate::hid::USAGE as i64;


/// One HID service, as read from the registry.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Candidate {
    pub registry_id: u64,
    pub vid: Option<i64>,
    pub pid: Option<i64>,
    pub usage_page: Option<i64>,
    pub usage: Option<i64>,
    /// ⚠️ IOKit's sizes **exclude** the report id, unlike `HidP_GetCaps`'
    /// 33 on Windows (`hid/caps.rs:97-104`). Recorded to settle that.
    pub max_input: Option<i64>,
    pub max_output: Option<i64>,
    /// Per-port, for the clock seed's `cid`. The Python reads `locationID` out
    /// of `ioreg -p IOUSB`; this is the same registry, with no spawn.
    pub location_id: Option<i64>,
    pub product: Option<String>,
    pub transport: Option<String>,
}

impl Candidate {
    /// A human name for logs and errors: the registry entry, in hex.
    pub fn name(&self) -> String {
        format!("IOHIDDevice {:#x}", self.registry_id)
    }

    /// The macOS analogue of Windows' `caps::Identity::check`, decided from
    /// properties before opening. ⚠️ IOKit's report sizes **exclude** the
    /// report id, so the right answer here is 32, where `HidP_GetCaps` says 33
    /// (measured in S2).
    pub fn check_sizes(&self) -> Result<(), String> {
        let want = Some(crate::proto::REPORT_LEN as i64);
        if self.max_input != want || self.max_output != want {
            return Err(format!(
                "report sizes in {:?} out {:?}, expected {} each (IOKit excludes the report id)",
                self.max_input,
                self.max_output,
                crate::proto::REPORT_LEN
            ));
        }
        Ok(())
    }

    pub fn is_ours(&self) -> bool {
        self.vid == Some(VID)
            && self.pid == Some(PID)
            && self.usage_page == Some(RAW_USAGE_PAGE)
            && self.usage == Some(RAW_USAGE)
    }
}

/// What the choice came to.
#[derive(Debug, PartialEq, Eq)]
pub enum Choice {
    One(u64),
    Absent,
    /// More than one raw-HID interface of this VID/PID: more than one of these
    /// keyboards. Refuse rather than pick, as Windows does.
    Ambiguous(Vec<u64>),
}

/// Pure: which of these, if exactly one, is ours.
pub fn choose(candidates: &[Candidate]) -> Choice {
    let ours: Vec<u64> = candidates
        .iter()
        .filter(|c| c.is_ours())
        .map(|c| c.registry_id)
        .collect();
    match ours.as_slice() {
        [] => Choice::Absent,
        [one] => Choice::One(*one),
        _ => Choice::Ambiguous(ours),
    }
}

/// Every IOHIDDevice service with our VID/PID, properties read, nothing opened.
///
/// Matching narrows by VID/PID in the registry itself, so services of other
/// devices (the UPS, the Stream Deck) are never even returned to us.
pub fn list() -> Result<Vec<(Candidate, Io)>, String> {
    unsafe {
        let matching = IOServiceMatching(c"IOHIDDevice".as_ptr());
        if matching.is_null() {
            return Err("IOServiceMatching(IOHIDDevice) returned NULL".into());
        }
        add_number(matching, "VendorID", VID);
        add_number(matching, "ProductID", PID);
        let mut iter: io_iterator_t = 0;
        // Consumes `matching`, success or not.
        let kr = IOServiceGetMatchingServices(0, matching as CFDictionaryRef, &mut iter);
        if kr != 0 {
            return Err(format!(
                "IOServiceGetMatchingServices: {}",
                ioreturn_name(kr)
            ));
        }
        let iter = Io(iter);
        let mut out = Vec::new();
        loop {
            let service = IOIteratorNext(iter.0);
            if service == 0 {
                break;
            }
            let service = Io(service);
            let mut registry_id = 0u64;
            IORegistryEntryGetRegistryEntryID(service.0, &mut registry_id);
            let num = |k: &str| property(service.0, k).and_then(|v| v.to_i64());
            let text = |k: &str| property(service.0, k).and_then(|v| v.to_string());
            let c = Candidate {
                registry_id,
                vid: num("VendorID"),
                pid: num("ProductID"),
                usage_page: num("PrimaryUsagePage"),
                usage: num("PrimaryUsage"),
                max_input: num("MaxInputReportSize"),
                max_output: num("MaxOutputReportSize"),
                location_id: num("LocationID")
                    .or_else(|| inherited(service.0, "locationID").and_then(|v| v.to_i64())),
                product: text("Product"),
                transport: text("Transport"),
            };
            out.push((c, service));
        }
        Ok(out)
    }
}

extern "C" {
    fn CFNumberCreate(
        alloc: CFAllocatorRef,
        the_type: CFIndex,
        value_ptr: *const std::os::raw::c_void,
    ) -> CFNumberRef;
    fn CFDictionarySetValue(
        dict: CFMutableDictionaryRef,
        key: *const std::os::raw::c_void,
        value: *const std::os::raw::c_void,
    );
}

unsafe fn add_number(dict: CFMutableDictionaryRef, key: &str, value: i64) {
    let k = Cf::string(key);
    let v = Cf::owned(CFNumberCreate(
        kCFAllocatorDefault,
        kCFNumberSInt64Type,
        &value as *const i64 as *const _,
    ))
    .expect("CFNumberCreate");
    CFDictionarySetValue(dict, k.as_ptr(), v.as_ptr()); // the dictionary retains both
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(id: u64, page: i64, usage: i64) -> Candidate {
        Candidate {
            registry_id: id,
            vid: Some(VID),
            pid: Some(PID),
            usage_page: Some(page),
            usage: Some(usage),
            max_input: Some(32),
            max_output: Some(32),
            location_id: Some(0x0014_1400),
            product: Some("AK820 PRO".into()),
            transport: Some("USB".into()),
        }
    }

    /// The board's collections: keyboard, mouse, consumer, system, raw HID.
    #[test]
    fn exactly_the_raw_hid_collection_is_chosen() {
        let all = [
            c(1, 0x01, 0x06),
            c(2, 0x01, 0x02),
            c(3, 0x0C, 0x01),
            c(4, 0x01, 0x80),
            c(5, RAW_USAGE_PAGE, RAW_USAGE),
        ];
        assert_eq!(choose(&all), Choice::One(5));
    }

    #[test]
    fn a_second_board_is_refused_not_guessed() {
        let all = [
            c(5, RAW_USAGE_PAGE, RAW_USAGE),
            c(9, RAW_USAGE_PAGE, RAW_USAGE),
        ];
        assert_eq!(choose(&all), Choice::Ambiguous(vec![5, 9]));
    }

    #[test]
    fn report_sizes_are_checked_without_the_report_id() {
        assert!(c(5, RAW_USAGE_PAGE, RAW_USAGE).check_sizes().is_ok());
        let mut windows_sized = c(5, RAW_USAGE_PAGE, RAW_USAGE);
        windows_sized.max_input = Some(33);
        assert!(windows_sized.check_sizes().is_err(), "33 is the Windows figure, not IOKit's");
        let mut none = c(5, RAW_USAGE_PAGE, RAW_USAGE);
        none.max_output = None;
        assert!(none.check_sizes().is_err());
    }

    #[test]
    fn a_right_page_wrong_usage_or_wrong_pid_is_not_ours() {
        let mut bootloader = c(7, RAW_USAGE_PAGE, RAW_USAGE);
        bootloader.pid = Some(0x7140);
        assert_eq!(
            choose(&[c(6, RAW_USAGE_PAGE, 0x62), bootloader]),
            Choice::Absent
        );
    }
}
