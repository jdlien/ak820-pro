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

/// Split a device-interface path into its four `#`-separated fields, if it has
/// the shape the Configuration Manager produces for a HID interface.
///
/// `\\?\HID#VID_0C45&PID_8009&MI_01#e&12502fcc&0&0000#{4d1e55b2-...}` is
/// `[r"\\?\HID", "vid_0c45&pid_8009&mi_01", "e&12502fcc&0&0000", "{4d1e55b2-...}"]`.
/// Anything else -- a different enumerator, a missing field, an extra one --
/// returns `None` and is refused rather than pattern-matched hopefully.
///
/// Lowercased, because the Configuration Manager is not consistent about case
/// and neither is the registry. This machine returns `MI_01` uppercase and
/// `Col02` mixed, in the same list.
fn fields(path: &str) -> Option<[String; 4]> {
    let lower = path.to_ascii_lowercase();
    let mut parts = lower.split('#');
    let prefix = parts.next()?;
    // `\\?\HID` is the only enumerator these come from. Refusing others is the
    // point: an unexpected shape is exactly when structural assumptions break.
    if prefix != r"\\?\hid" {
        return None;
    }
    let hardware = parts.next()?.to_string();
    let instance = parts.next()?.to_string();
    let class = parts.next()?.to_string();
    if parts.next().is_some() || hardware.is_empty() {
        return None;
    }
    Some([prefix.to_string(), hardware, instance, class])
}

/// The hardware-id field, lowercased, or `None` if the path is not one we
/// recognise.
///
/// ⚠️ This is the only field whose contents describe the *device*. The third
/// field is the device-instance id, which is largely vendor-chosen text, and
/// the fourth is the interface class GUID.
pub fn hardware_id(path: &str) -> Option<String> {
    fields(path).map(|f| f[1].clone())
}

/// Does this interface path name the given vendor and product?
///
/// ⚠️ **The pair must appear in the hardware-id field**, as a whole token
/// delimited by `&`. Two separate mistakes are possible here and this has made
/// both:
///
/// 1. A bare `contains()` accepts a longer id that embeds ours -- `VID_10C45`.
/// 2. A delimiter-checked search of the **whole path** accepts our ids
///    appearing anywhere, including the device-instance field, which is not a
///    statement about what the device is.
///
/// The second one is not hypothetical. The 2026-09-06 audit produced this,
/// and the previous implementation matched it:
///
/// ```text
/// \\?\HID#VID_051D&PID_0002#VID_0C45&PID_8009#{4d1e55b2-f16f-11cf-88cb-001111000030}
/// ```
///
/// That is the **UPS's** hardware id with our ids sitting in the instance
/// field -- precisely the device this filter exists to never open, and the
/// post-open attribute check cannot help because the damage is the open.
///
/// Bluetooth-attached HID paths carry no `VID_` field in this form and so never
/// match, which is correct: this board is USB.
pub fn matches_device(path: &str, vid: u16, pid: u16) -> bool {
    let Some(hardware) = hardware_id(path) else {
        return false;
    };
    let needle = format!("vid_{vid:04x}&pid_{pid:04x}");
    let Some(at) = hardware.find(&needle) else {
        return false;
    };
    // Within the hardware id, fields are `&`-separated: `vid_x&pid_y&mi_01`.
    let before_ok = at == 0;
    let after = at + needle.len();
    let after_ok = after == hardware.len() || hardware.as_bytes()[after] == b'&';
    before_ok && after_ok
}

/// Is this the interface QMK puts raw HID on?
///
/// A *hint*, never a decision: it orders candidates so the usual case opens
/// exactly one device. The usage page still decides, after opening, because the
/// interface number depends on which USB features the firmware was built with
/// and would change silently if that changed.
pub fn is_raw_hid_hint(path: &str) -> bool {
    // Field-restricted for the same reason `matches_device` is: `&mi_01`
    // appearing in an instance id says nothing about the interface.
    hardware_id(path).is_some_and(|h| h.split('&').any(|f| f == "mi_01"))
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

    /// ⚠️ Measured on this machine: two of the board's five real paths carry a
    /// `\KBD` suffix after the class GUID — the legacy keyboard-device alias.
    /// It lands inside the fourth field, so the four-field shape still holds,
    /// but a stricter parse demanding the path END at the GUID would reject two
    /// of this board's own collections. Pinned because tightening the filter is
    /// exactly when that would get broken.
    #[test]
    fn accepts_the_live_paths_that_carry_a_kbd_suffix() {
        const WITH_KBD: &str = r"\\?\HID#VID_0C45&PID_8009&MI_02&Col03#e&11870df6&0&0002#{4d1e55b2-f16f-11cf-88cb-001111000030}\KBD";
        assert!(matches_device(WITH_KBD, VID, PID));
        assert!(!is_raw_hid_hint(WITH_KBD), "Col03 is the NKRO keyboard");
        assert_eq!(
            hardware_id(WITH_KBD).as_deref(),
            Some("vid_0c45&pid_8009&mi_02&col03")
        );
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

    /// ⚠️ The 2026-09-06 audit's counterexample, and the reason the match is
    /// restricted to the hardware-id field. This is the **UPS** -- the exact
    /// device this module exists to never open -- with our ids sitting in the
    /// device-instance field, where they say nothing about what the device is.
    /// The delimiter-checked whole-path search that preceded this accepted it.
    #[test]
    fn rejects_our_ids_planted_in_the_instance_field() {
        let planted =
            r"\\?\HID#VID_051D&PID_0002#VID_0C45&PID_8009#{4d1e55b2-f16f-11cf-88cb-001111000030}";
        assert!(
            !matches_device(planted, VID, PID),
            "our ids outside the hardware-id field are not our device"
        );
        assert!(
            matches_device(planted, 0x051D, 0x0002),
            "... and the hardware id still says whose it really is"
        );
    }

    /// The same trick against the interface hint, which orders what gets opened
    /// first.
    #[test]
    fn rejects_an_interface_hint_planted_in_the_instance_field() {
        let planted =
            r"\\?\HID#VID_0C45&PID_8009&MI_00#e&mi_01&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}";
        assert!(matches_device(planted, VID, PID), "it is still our board");
        assert!(
            !is_raw_hid_hint(planted),
            "but MI_00 is the keyboard, whatever the instance field says"
        );
    }

    /// Shapes that are not a HID interface path at all. Refused rather than
    /// parsed hopefully -- an unexpected form is exactly when the structural
    /// assumptions above stop holding.
    #[test]
    fn rejects_paths_that_are_not_hid_interface_paths() {
        for odd in [
            r"\\?\USB#VID_0C45&PID_8009#x#{g}",          // wrong enumerator
            r"\\?\HID#VID_0C45&PID_8009#x",              // too few fields
            r"\\?\HID#VID_0C45&PID_8009#x#{g}#extra",    // too many
            r"\\?\HID##VID_0C45&PID_8009#{g}",           // empty hardware id
            r"HID#VID_0C45&PID_8009&MI_01#x#{g}",        // no prefix
        ] {
            assert!(!matches_device(odd, VID, PID), "{odd}");
        }
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
