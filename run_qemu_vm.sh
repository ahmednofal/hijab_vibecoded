#!/bin/bash
# Simple QEMU script to run Windows 11 VM for testing

ISO_PATH="/home/nofal/personal_dev/hijab_by_copilot_windows/tiny11_23H2_x64.iso"
DISK_IMG="$HOME/.local/share/qemu/windows11-hijab.qcow2"
VM_NAME="Windows11-Hijab-Test"

# Create disk image directory if it doesn't exist
mkdir -p "$(dirname "$DISK_IMG")"

# Create disk image if it doesn't exist (50GB)
if [ ! -f "$DISK_IMG" ]; then
    echo "Creating virtual disk (50GB)..."
    qemu-img create -f qcow2 "$DISK_IMG" 50G
fi

echo "============================================================"
echo " Starting Windows 11 VM for Hijab by Copilot Testing"
echo "============================================================"
echo " VM: $VM_NAME"
echo " Disk: $DISK_IMG"
echo " ISO: $ISO_PATH"
echo " Project shared at: /home/nofal/personal_dev/hijab_by_copilot_windows"
echo ""
echo " First boot: Install Windows"
echo " Later boots: Windows will start directly"
echo ""
echo " Press Ctrl+Alt+G to release mouse/keyboard"
echo " Press Ctrl+Alt+F to toggle fullscreen"
echo "============================================================"
echo ""

# Create UEFI vars file if it doesn't exist (non-MS = no Secure Boot)
EFIVARS_FILE="$HOME/.local/share/qemu/efivars-$VM_NAME.fd"
if [ ! -f "$EFIVARS_FILE" ]; then
    echo "Creating UEFI variables file..."
    mkdir -p "$(dirname "$EFIVARS_FILE")"
    cp /usr/share/OVMF/OVMF_VARS_4M.fd "$EFIVARS_FILE" 2>/dev/null || \
    cp /usr/share/OVMF/OVMF_VARS.fd "$EFIVARS_FILE" 2>/dev/null || \
    dd if=/dev/zero of="$EFIVARS_FILE" bs=1M count=64
fi

OVMF_CODE="/usr/share/OVMF/OVMF_CODE_4M.fd"
if [ ! -f "$OVMF_CODE" ]; then
    OVMF_CODE="/usr/share/OVMF/OVMF_CODE.fd"
fi

# Run QEMU (no Secure Boot, no TPM — Tiny11 doesn't need either)
qemu-system-x86_64 \
    -name "$VM_NAME" \
    -enable-kvm \
    -cpu host \
    -smp 2 \
    -m 4G \
    -machine q35 \
    -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
    -drive if=pflash,format=raw,file="$EFIVARS_FILE" \
    -drive file="$DISK_IMG",format=qcow2,id=hd0,if=none \
    -device ich9-ahci,id=ahci \
    -device ide-hd,drive=hd0,bus=ahci.0 \
    -cdrom "$ISO_PATH" \
    -boot order=d,menu=on \
    -netdev user,id=net0 \
    -device e1000,netdev=net0 \
    -vga std \
    -display gtk \
    -usb \
    -device usb-tablet

echo ""
echo "VM exited."
