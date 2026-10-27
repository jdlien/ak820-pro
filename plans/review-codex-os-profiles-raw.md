No flash-safety blocker found in `0ada282c..bf29a081` or the listed host changes.

- [profiles.c:179](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:179): pair/pending handling is consistent across set, delete, format, restore commit, HC 0/6 and tick.
- [profiles.c:475](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:475): boot only initializes the side; countdown handles bounce and waits for recovery/restores. Loads cancel edits/previews. Rename retains its explicit slot.
- [ak820profiles.py:123](/C:/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:123): both conversion directions and normalization agree with the board’s commit semantics.
- [sleep.c:178](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:178): the switch isn’t a wake source; sleeping flips take effect after wake and recovery.

Tests/build weren’t rerun: process execution was denied. The reported 136 B heap gap clears the floor by 8 B.