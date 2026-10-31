#!/usr/bin/env bash
# QMK's own wear-leveling unit tests (quantum/wear_leveling/tests, the
# defines from its rules.mk), built against shim/, a minimal stand-in for
# googletest, since lib/googletest is not checked out. The board's
# wear_leveling.c changes the 8-byte store's line (the 10-31 audit, F-010),
# so wear_leveling_8byte.cpp carries its expectations. CXX picks the
# compiler (default c++).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
t="$q/quantum/wear_leveling/tests"
cxx="${CXX:-c++}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
fails=0
build() {   # name, defines
    local name="$1"; shift
    "$cc" -std=gnu11 -g -O1 -DWEAR_LEVELING_TESTS "$@" -I"$q/lib/fnv" -I"$q/quantum/wear_leveling" -I"$q/quantum" -c \
        "$q/quantum/wear_leveling/wear_leveling.c" -o "$o/$name-wl.o"
    for c in qmk_fnv_type_validation hash_32a hash_64a; do
        "$cc" -std=gnu11 -g -O1 "$@" -I"$q/lib/fnv" -I"$q/quantum" -c "$q/lib/fnv/$c.c" -o "$o/$name-$c.o"
    done
    "$cxx" -std=gnu++17 -g -O1 -Wno-c99-designator -DWEAR_LEVELING_TESTS "$@" -I"$here/shim" -I"$q/lib/fnv" -I"$q/quantum/wear_leveling" -I"$q/quantum" -I"$t" \
        "$t/backing_mocks.cpp" "$t/$name.cpp" "$here/main.cpp" "$o/$name"-*.o -o "$o/$name"
    echo "== $name"
    "$o/$name" || fails=$((fails + 1))
}
cc="${CC:-cc}"
build wear_leveling_general -DBACKING_STORE_WRITE_SIZE=2 -DWEAR_LEVELING_BACKING_SIZE=48 -DWEAR_LEVELING_LOGICAL_SIZE=16
build wear_leveling_2byte_optimized_writes -DBACKING_STORE_WRITE_SIZE=2 -DWEAR_LEVELING_BACKING_SIZE=65536 -DWEAR_LEVELING_LOGICAL_SIZE=32768
build wear_leveling_2byte -DBACKING_STORE_WRITE_SIZE=2 -DWEAR_LEVELING_BACKING_SIZE=48 -DWEAR_LEVELING_LOGICAL_SIZE=16
build wear_leveling_4byte -DBACKING_STORE_WRITE_SIZE=4 -DWEAR_LEVELING_BACKING_SIZE=48 -DWEAR_LEVELING_LOGICAL_SIZE=16
build wear_leveling_8byte -DBACKING_STORE_WRITE_SIZE=8 -DWEAR_LEVELING_BACKING_SIZE=48 -DWEAR_LEVELING_LOGICAL_SIZE=16
[ "$fails" -eq 0 ] && echo "RESULT: all five suites pass" || { echo "RESULT: $fails suite(s) failed"; exit 1; }
