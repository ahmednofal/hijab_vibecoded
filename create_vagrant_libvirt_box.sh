#!/bin/bash
# Create a Vagrant box from your QEMU Windows installation for libvirt

QEMU_DISK="$HOME/.local/share/qemu/windows11-hijab.qcow2"
BOX_NAME="windows11-hijab"
BOX_FILE="$BOX_NAME.box"

echo "============================================================"
echo " Creating Vagrant Box from QEMU VM (libvirt)"
echo "============================================================"
echo ""

# Check if QEMU disk exists
if [ ! -f "$QEMU_DISK" ]; then
    echo "ERROR: QEMU disk not found at: $QEMU_DISK"
    echo "Please install Windows first using ./run_qemu_vm.sh"
    exit 1
fi

echo "Step 1: Preparing libvirt disk..."
LIBVIRT_POOL="$HOME/.local/share/libvirt/images"
mkdir -p "$LIBVIRT_POOL"
LIBVIRT_DISK="$LIBVIRT_POOL/$BOX_NAME.qcow2"

if [ -f "$LIBVIRT_DISK" ]; then
    echo "Libvirt disk already exists: $LIBVIRT_DISK"
else
    echo "Copying disk to libvirt pool..."
    cp "$QEMU_DISK" "$LIBVIRT_DISK"
fi

echo ""
echo "Step 2: Creating Vagrant metadata..."
BUILD_DIR="/tmp/vagrant-box-build-$$"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Create metadata.json
cat > metadata.json << 'EOF'
{
  "provider": "libvirt",
  "format": "qcow2",
  "virtual_size": 50
}
EOF

# Create Vagrantfile for the box
cat > Vagrantfile << 'EOF'
Vagrant.configure("2") do |config|
  config.vm.provider :libvirt do |libvirt|
    libvirt.driver = "kvm"
    libvirt.memory = 4096
    libvirt.cpus = 2
    libvirt.graphics_type = "spice"
  end
end
EOF

# Copy the disk image
echo "Copying disk image..."
cp "$LIBVIRT_DISK" box.img

echo ""
echo "Step 3: Packaging as Vagrant box..."
tar czf "$BOX_FILE" metadata.json Vagrantfile box.img

echo ""
echo "Step 4: Adding box to Vagrant..."
vagrant box add "$BOX_NAME" "$BOX_FILE" --force

echo ""
echo "Step 5: Cleaning up..."
cd -
rm -rf "$BUILD_DIR"

echo ""
echo "============================================================"
echo " ✅ Vagrant box created successfully!"
echo "============================================================"
echo ""
echo "Box name: $BOX_NAME"
echo ""
echo "To use with Vagrant:"
echo "  cd /home/nofal/personal_dev/hijab_by_copilot_windows"
echo "  vagrant up --provider=libvirt"
echo ""
echo "To manage:"
echo "  vagrant status    # Check VM status"
echo "  vagrant ssh       # SSH into VM (if configured)"
echo "  vagrant halt      # Stop VM"
echo "  vagrant destroy   # Delete VM"
echo ""
