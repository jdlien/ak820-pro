//! Deciding which device-interface paths belong to this keyboard.
//!
//! This module is pure string logic and holds no handles, which is the point:
//! it is what lets discovery narrow the Configuration Manager's list to our own
//! device **before opening anything**.
//!
//! ⚠️ Why that matters more than it looks. `hidapi`'s enumeration opens every
//! HID device on the machine to read its attributes, and
//! `../jdrgb/docs/ups-wedge-incident.md` records that twice wedging an APC
//! Back-UPS on this machine -- every request failing from every process,
//! recoverable only by physically replugging -- while `../jdups` held a latched
//! outage it could no longer see the end of. We match text instead.
//!
//! ⚠️ And why matching is not enough on its own. Microsoft documents these
//! symbolic names as **opaque**: a path match is a *candidate selector, not
//! proof of identity*. The caller must still confirm with `HidD_GetAttributes`
//! and the usage page after opening. Post-open checks stop a wrong *write*;
//! they cannot un-open a device, which is why this filter is deliberately
//! strict rather than a loose substring search.

/// The AJAZZ AK820 Pro. Same ids in bootloader-adjacent tooling, so the usage
/// page check after opening is what actually distinguishes the raw-HID
/// interface from the keyboard's other collections.
pub const VID: u16 = 0x0C45;
pub const PID: u16 = 0x8009;

/// QMK raw HID. Verified on this board: interface `MI_01`.
pub const USAGE_PAGE: u16 = 0xFF60;
pub const USAGE: u16 = 0x61;

/// Does this interface path name the given vendor and product?
///
/// Requires the `vid_xxxx&pid_xxxx` pair to appear as a **bounded token** in
/// the hardware-id portion -- delimited by `#` or `&`, not merely contained.
/// A bare `contains()` would accept a longer id that happens to embed ours
/// (`VID_10C45`), and Bluetooth-attached HID paths, which carry no `VID_`
/// field in this form, simply never match. Case-insensitive: the Configuration
/// Manager is not consistent about case and neither is the registry.
pub fn matches_device(path: &str, vid: u16, pid: u16) -> bool {
    let lower = path.to_ascii_lowercase();
    let needle = format!("vid_{vid:04x}&pid_{pid:04x}");
    let Some(at) = lower.find(&needle) else {
        return false;
    };
    let before_ok = at == 0 || matches!(lower.as_bytes()[at - 1], b'#' | b'&' | b'\\');
    let after = at + needle.len();
    let after_ok = after == lower.len() || matches!(lower.as_bytes()[after], b'#' | b'&');
    before_ok && after_ok
}

/// Is this the interface QMK puts raw HID on?
///
/// A *hint*, never a decision: it orders candidates so the usual case opens
/// exactly one device. The usage page still decides, after opening, because the
/// interface number depends on which USB features the firmware was built with
/// and would change silently if that changed.
pub fn is_raw_hid_hint(path: &str) -> bool {
    path.to_ascii_lowercase().contains("&mi_01")
}

/// Candidate interfaces for this board, best guess first.
///
/// Takes the already-listed paths rather than calling the Configuration Manager
/// itself, so the ordering and filtering are testable without a device.
pub fn candidates<'a>(paths: &'a [String], vid: u16, pid: u16) -> Vec<&'a str> {
    let mut out: Vec<&str> = paths
        .iter()
        .map(String::as_str)
        .filter(|p| matches_device(p, vid, pid))
        .collect();
    // Stable partition: the MI_01 hint first, everything else in listed order.
    out.sort_by_key(|p| !is_raw_hid_hint(p));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Measured on this machine 2026-09-05 -- the real raw-HID path.
    const REAL: &str =
        r"\\?\HID#VID_0C45&PID_8009&MI_01#e&12502fcc&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}";
    /// The keyboard's other collections, same board.
    const KEYBOARD_IF: &str =
        r"\\?\HID#VID_0C45&PID_8009&MI_00#d&1c9b2c77&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}";
    const CONSUMER_IF: &str =
        r"\\?\HID#VID_0C45&PID_8009&MI_02&COL02#e&11870df6&0&0001#{4d1e55b2-f16f-11cf-88cb-001111000030}";

    #[test]
    fn accepts_the_real_interface() {
        assert!(matches_device(REAL, VID, PID));
        assert!(is_raw_hid_hint(REAL));
    }

    #[test]
    fn accepts_the_boards_other_collections() {
        // They are ours; the usage-page check after opening rejects them, not this.
        assert!(matches_device(KEYBOARD_IF, VID, PID));
        assert!(matches_device(CONSUMER_IF, VID, PID));
        assert!(!is_raw_hid_hint(KEYBOARD_IF));
    }

    #[test]
    fn case_insensitive() {
        assert!(matches_device(&REAL.to_ascii_lowercase(), VID, PID));
        assert!(matches_device(&REAL.to_ascii_uppercase(), VID, PID));
    }

    #[test]
    fn rejects_other_vendors() {
        // The UPS and the RGB controller from the sibling projects: the exact
        // devices that must never be opened by this program.
        let ups = r"\\?\HID#VID_051D&PID_0002#6&1a2b3c4d&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}";
        let aura = r"\\?\HID#VID_0B05&PID_19AF&MI_02#7&2f1e0c5b&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}";
        assert!(!matches_device(ups, VID, PID));
        assert!(!matches_device(aura, VID, PID));
    }

    #[test]
    fn rejects_same_vid_different_pid() {
        // 0x7140 is this board's own BOOTLOADER. Correctly not a match for the
        // running firmware's PID -- flashing is ak820ctl's job, not ours.
        let boot = r"\\?\HID#VID_0C45&PID_7140#6&aabbccdd&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}";
        assert!(!matches_device(boot, VID, PID));
        assert!(matches_device(boot, 0x0C45, 0x7140));
    }

    #[test]
    fn rejects_embedded_ids_that_merely_contain_ours() {
        // The bug a bare contains() would have: these must NOT match.
        assert!(!matches_device(r"\\?\HID#VID_10C45&PID_8009#x", VID, PID));
        assert!(!matches_device(r"\\?\HID#VID_0C45&PID_80099#x", VID, PID));
        assert!(!matches_device(r"\\?\HID#XVID_0C45&PID_8009#x", VID, PID));
    }

    #[test]
    fn rejects_paths_without_the_pair() {
        // Bluetooth HID paths carry no VID_/PID_ fields in this form.
        assert!(!matches_device(r"\\?\BTHENUM#{00001124-0000-1000-8000-00805f9b34fb}_LOCALMFG&0000#7&1", VID, PID));
        assert!(!matches_device("", VID, PID));
        assert!(!matches_device("vid_0c45", VID, PID));
    }

    #[test]
    fn candidates_put_the_raw_hid_hint_first_and_drop_strangers() {
        let ups = r"\\?\HID#VID_051D&PID_0002#6&1a2b3c4d&0&0000#{g}".to_string();
        let paths = vec![
            KEYBOARD_IF.to_string(),
            ups,
            REAL.to_string(),
            CONSUMER_IF.to_string(),
        ];
        let got = candidates(&paths, VID, PID);
        assert_eq!(got.len(), 3, "the UPS must not be a candidate");
        assert_eq!(got[0], REAL, "MI_01 must be tried first");
        assert!(!got.iter().any(|p| p.contains("051D")));
    }

    #[test]
    fn candidates_is_empty_when_the_board_is_absent() {
        let paths = vec![r"\\?\HID#VID_051D&PID_0002#6&x&0&0000#{g}".to_string()];
        assert!(candidates(&paths, VID, PID).is_empty());
    }
}
