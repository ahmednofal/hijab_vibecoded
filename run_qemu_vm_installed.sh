#!/bin/bash
# Run already-installed Windows 11 VM (without ISO)

DISK_IMG="$HOME/.local/share/qemu/windows11-hijab.qcow2"
VM_NAME="Windows11-Hijab-Test"

if [ ! -f "$DISK_IMG" ]; then
    echo "ERROR: VM disk not found at: $DISK_IMG"
    echo "Please run ./run_qemu_vm.sh first to install Windows."
    exit 1
fi

echo "============================================================"
echo " Starting Windows VM"
echo "============================================================"
echo ""
echo " Your project folder is shared via SMB"
echo " In Windows, map network drive: \\\\10.0.2.4\\qemu"
echo ""
echo " Controls:"
echo "   Ctrl+Alt+G - Release mouse/keyboard"
echo "   Ctrl+Alt+F - Toggle fullscreen"  
echo "   Ctrl+Alt+Q - Quit VM"
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

# Run without CD-ROM (boots from disk)
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
    -boot c \
    -netdev user,id=net0,smb="$PWD" \
    -device e1000,netdev=net0 \
    -vga std \
    -display gtk \
    -usb \
    -device usb-tablet

echo ""
echo "VM exited."
