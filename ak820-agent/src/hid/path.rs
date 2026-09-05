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

/// Split the Configuration Manager's `REG_MULTI_SZ`-shaped answer into paths.
///
/// `CM_Get_Device_Interface_ListW` fills one buffer with NUL-separated strings
/// terminated by a second NUL, and the buffer it sizes is usually longer than
/// the data, so the tail is zero padding rather than a run of empty paths.
/// Empty entries are dropped for that reason, not out of tidiness.
pub fn split_multi_sz(buf: &[u16]) -> Vec<String> {
    buf.split(|&c| c == 0)
        .filter(|s| !s.is_empty())
        .map(String::from_utf16_lossy)
        .collect()
}

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

/// The hardware-id field of a device-interface path, lowercased.
///
/// `\\?\HID#VID_0C45&PID_8009&MI_01#e&12502fcc&0&0000#{guid}` has four
/// `#`-separated fields; this is the second, `vid_0c45&pid_8009&mi_01`. The
/// *third* is the device-instance id, and it deliberately is not used here: one
/// board's collections each carry a different instance, so instances cannot
/// tell one keyboard's several interfaces from several keyboards.
pub fn hardware_id(path: &str) -> Option<String> {
    let field = path.split('#').nth(1)?;
    (!field.is_empty()).then(|| field.to_ascii_lowercase())
}

/// Candidate paths that name the same interface more than once.
///
/// One keyboard cannot expose the same interface and collection twice, so a
/// repeat means a **second identical keyboard**. That is the case the plan says
/// to refuse and report rather than pick a side in, and deciding it from the
/// path list costs nothing and opens nothing.
pub fn duplicate_interfaces<'a>(paths: &[&'a str]) -> Vec<&'a str> {
    let ids: Vec<Option<String>> = paths.iter().map(|p| hardware_id(p)).collect();
    paths
        .iter()
        .zip(&ids)
        .filter(|(_, id)| id.is_some() && ids.iter().filter(|other| *other == *id).count() > 1)
        .map(|(p, _)| *p)
        .collect()
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
    fn hardware_id_is_the_second_field() {
        assert_eq!(
            hardware_id(REAL).as_deref(),
            Some("vid_0c45&pid_8009&mi_01")
        );
        assert_eq!(
            hardware_id(CONSUMER_IF).as_deref(),
            Some("vid_0c45&pid_8009&mi_02&col02"),
            "the collection index is part of the interface's identity"
        );
        assert_eq!(hardware_id("nothing-shaped-like-a-path"), None);
    }

    /// One board's collections all differ, so nothing is a duplicate -- and the
    /// instance ids differing between them is exactly why instances cannot be
    /// used for this.
    #[test]
    fn one_keyboards_collections_are_not_duplicates() {
        let paths = [REAL, KEYBOARD_IF, CONSUMER_IF];
        assert!(duplicate_interfaces(&paths).is_empty());
    }

    /// Two of the same keyboard: the same interface, a different instance. The
    /// case the plan says to refuse rather than pick a side in.
    #[test]
    fn a_second_identical_keyboard_is_a_duplicate() {
        let second = r"\\?\HID#VID_0C45&PID_8009&MI_01#f&7ac31d02&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}";
        let paths = [REAL, KEYBOARD_IF, second];
        let dupes = duplicate_interfaces(&paths);
        assert_eq!(dupes.len(), 2, "both must be reported, not one chosen");
        assert!(dupes.contains(&REAL) && dupes.contains(&second));
    }

    #[test]
    fn multi_sz_splits_and_ignores_the_zero_padding() {
        let mut buf: Vec<u16> = Vec::new();
        for p in [REAL, KEYBOARD_IF] {
            buf.extend(p.encode_utf16());
            buf.push(0);
        }
        buf.push(0); // the terminating NUL of the multi-sz
        buf.extend([0u16; 40]); // ... and the slack the sizing call left us
        let got = split_multi_sz(&buf);
        assert_eq!(got, vec![REAL.to_string(), KEYBOARD_IF.to_string()]);
    }

    #[test]
    fn multi_sz_of_nothing_is_no_paths() {
        assert!(split_multi_sz(&[]).is_empty());
        assert!(split_multi_sz(&[0, 0]).is_empty());
    }

    #[test]
    fn candidates_is_empty_when_the_board_is_absent() {
        let paths = vec![r"\\?\HID#VID_051D&PID_0002#6&x&0&0000#{g}".to_string()];
        assert!(candidates(&paths, VID, PID).is_empty());
    }
}
