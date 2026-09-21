#!/bin/sh
# Only for the observed UF1003 MB V02 / OpenStick LK1ST partition layout.
# No MTD fallback and no writes outside boot and rootfs.
REQUIRE_IMAGE_METADATA=1
RAMFS_COPY_BIN="$RAMFS_COPY_BIN sha256sum head readlink df"

ufi_error() {
    echo "UFI upgrade: $*" >&2
    return 1
}

ufi_check_layout() {
    [ "$(cat /tmp/sysinfo/board_name)" = 'thwc,ufi001c' ] ||
        { ufi_error 'Board mismatch'; return 1; }
    grep -qE '(^| )root=/dev/mmcblk0p14( |$)' /proc/cmdline ||
        { ufi_error 'Unexpected root device'; return 1; }
    local spec part label start sectors
    for spec in '11 aboot 524288 2048' '12 boot 526336 131072' \
                '13 devinfo 657408 2048' '14 rootfs 659456 6975455'; do
        set -- $spec
        part="$1"; label="$2"; start="$3"; sectors="$4"
        [ -b "/dev/mmcblk0p$part" ] &&
        grep -qx "PARTNAME=$label" "/sys/class/block/mmcblk0p$part/uevent" &&
        [ "$(cat /sys/class/block/mmcblk0p$part/start)" = "$start" ] &&
        [ "$(cat /sys/class/block/mmcblk0p$part/size)" = "$sectors" ] ||
            { ufi_error "Partition $part does not match the tested layout"; return 1; }
    done
}

# stdout-only extraction: archive paths are never extracted onto the running OS.
ufi_member() { tar -xOf "$1" "$2"; }
ufi_digest() { sha256sum | cut -d ' ' -f 1; }

ufi_check_package() (
    set -o pipefail
    set -f
    local image="$1" list control item bytes
    [ -f "$image" ] || { ufi_error 'Missing image'; exit 1; }
    bytes="$(wc -c < "$image")" || exit 1
    [ "$bytes" -gt 10240 ] && [ "$bytes" -le 167772160 ] ||
        { ufi_error 'Package must be at most 160 MiB for this 383 MiB device'; exit 1; }
    fwtool -q -i /dev/null "$image" || { ufi_error 'Missing/corrupt fwtool metadata'; exit 1; }
    list="$(tar -tf "$image")" || exit 1
    [ "$list" = "CONTROL
boot.img
root.ext4.gz" ] || { ufi_error 'Unexpected archive members/order'; exit 1; }
    # Reject symlinks, directories and hard links, including duplicate names.
    list="$(tar -tvf "$image")" || exit 1
    [ "$(printf '%s\n' "$list" | grep -c '^-')" = 3 ] ||
        { ufi_error 'Archive members must be regular files'; exit 1; }
    control="$(ufi_member "$image" CONTROL)" || exit 1
    [ "${#control}" -le 300 ] || exit 1
    set -- $control
    [ "$#" = 6 ] && [ "$1" = 'UFI003-EXT4-1' ] ||
        { ufi_error 'Unsupported package format'; exit 1; }
    case "$2" in ''|*[!0-9]*) exit 1;; esac
    [ "${#2}" -le 8 ] && [ "$2" -ge 2048 ] && [ "$2" -le 67108864 ] || exit 1
    # v1 deliberately supports only the tested 512 MiB ext4 image size.
    [ "$4" = 536870912 ] || { ufi_error 'Root image must be 512 MiB'; exit 1; }
    for item in "$3" "$5" "$6"; do
        [ "${#item}" = 64 ] || exit 1
        case "$item" in *[!0-9a-f]*) exit 1;; esac
    done
    [ "$(ufi_member "$image" boot.img | wc -c)" = "$2" ] &&
    [ "$(ufi_member "$image" boot.img | ufi_digest)" = "$3" ] &&
    [ "$(ufi_member "$image" root.ext4.gz | ufi_digest)" = "$6" ] ||
        { ufi_error 'Payload checksum or length mismatch'; exit 1; }
    [ "$(ufi_member "$image" boot.img | { dd bs=8 count=1 2>/dev/null; cat >/dev/null; })" = 'ANDROID!' ] ||
        { ufi_error 'Not an Android boot image'; exit 1; }
    # v1 uses one gzip member; its little-endian ISIZE must be 512 MiB.
    item="$(ufi_member "$image" root.ext4.gz | tail -c 4 | hexdump -v -e '4/1 "%02x"')" || exit 1
    [ "$item" = 00000020 ] || { ufi_error 'Gzip size trailer mismatch'; exit 1; }
    # Full inflation/hash verification happens in RAM before ANY write. Avoid
    # hashing 512 MiB through a slow A53 during LuCI's timed validation RPC.
    if [ "${ufi_full_check:-0}" = 1 ]; then
        item="$(ufi_member "$image" root.ext4.gz | gzip -dc | ufi_digest)" || exit 1
        [ "$item" = "$5" ] || { ufi_error 'Uncompressed root checksum mismatch'; exit 1; }
    fi
)

platform_check_image() {
    [ "$#" = 1 ] || return 1
    ufi_check_layout && ufi_check_package "$1" || return 1
    # The upload already occupies /tmp. Leave room for the RAM root and backup.
    [ "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)" -ge 49152 ] &&
    [ "$(df -Pk /tmp | awk 'END {print $4}')" -ge 24576 ] ||
        { ufi_error 'Need 48 MiB available RAM and 24 MiB free in /tmp'; return 1; }
}

ufi_check_ram_stage() {
    [ "$(awk '$2 == "/" {print $3}' /proc/mounts)" = tmpfs ] ||
        { ufi_error 'Refusing to write while root is not in RAM'; return 1; }
    local part dev
    for part in 12 14; do
        dev="$(cat /sys/class/block/mmcblk0p$part/dev)" || return 1
        if awk -v dev="$dev" '$3 == dev {found=1} END {exit !found}' /proc/self/mountinfo; then
            ufi_error "Partition $part is still mounted"; return 1
        fi
        [ -z "$(ls -A /sys/class/block/mmcblk0p$part/holders)" ] || return 1
    done
    [ "$(wc -l < /proc/swaps)" = 1 ] ||
        { ufi_error 'Active swap is not supported during upgrade'; return 1; }
}

# do_stage2 does not check the platform function's return status. All failures
# here must EXIT its shell, preventing a false success message/automatic reboot.
platform_do_upgrade() {
    set -o pipefail
    local ufi_full_check=1
    ufi_check_layout && ufi_check_ram_stage && ufi_check_package "$1" || exit 1
    local image="$1" control boot_size boot_sha root_size root_sha digest dest
    control="$(ufi_member "$image" CONTROL)" || exit 1
    set -- $control
    boot_size="$2"; boot_sha="$3"; root_size="$4"; root_sha="$5"
    if [ -n "$UPGRADE_BACKUP" ]; then
        [ -f "$UPGRADE_BACKUP" ] && gzip -t "$UPGRADE_BACKUP" &&
            tar -tzf "$UPGRADE_BACKUP" >/dev/null || exit 1
        [ "$(wc -c < "$UPGRADE_BACKUP")" -le 8388608 ] ||
            { ufi_error 'Configuration backup exceeds 8 MiB'; exit 1; }
    fi
    echo 'UFI upgrade: writing rootfs from RAM; keep power connected.' >&2
    ufi_member "$image" root.ext4.gz | gzip -dc | dd of=/dev/mmcblk0p14 bs=1M conv=fsync || exit 1
    digest="$(head -c "$root_size" /dev/mmcblk0p14 | ufi_digest)" || exit 1
    [ "$digest" = "$root_sha" ] || { ufi_error 'Rootfs readback failed'; exit 1; }
    # The standard preinit restore hook reads /sysupgrade.tgz on next boot.
    if [ -n "$UPGRADE_BACKUP" ]; then
        dest=/tmp/ufi-new-root
        mkdir "$dest" && mount -t ext4 -o rw /dev/mmcblk0p14 "$dest" || exit 1
        rm -f "$dest/sysupgrade.tgz" "$dest/etc/ufi-config-restored" || exit 1
        cp "$UPGRADE_BACKUP" "$dest/sysupgrade.tgz" &&
            touch "$dest/etc/ufi-config-restored" && sync && umount "$dest" || exit 1
        rmdir "$dest" || exit 1
    fi
    # Switch kernel last, after the root payload and config are durable.
    ufi_member "$image" boot.img | dd of=/dev/mmcblk0p12 bs=1M conv=fsync || exit 1
    digest="$(head -c "$boot_size" /dev/mmcblk0p12 | ufi_digest)" || exit 1
    [ "$digest" = "$boot_sha" ] || { ufi_error 'Boot readback failed'; exit 1; }
    sync
    echo 'UFI upgrade: both partitions verified; ready to reboot.' >&2
}
