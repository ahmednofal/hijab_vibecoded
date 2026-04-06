#!/bin/bash
# Create a Vagrant libvirt box from the QEMU disk

DISK_IMG="$HOME/.local/share/qemu/windows11-hijab.qcow2"
BOX_NAME="windows11-hijab"
OUTPUT_BOX="${BOX_NAME}.box"

echo "============================================================"
echo " Creating Vagrant Libvirt Box"
echo "============================================================"
echo ""

# Check if disk exists
if [ ! -f "$DISK_IMG" ]; then
    echo "ERROR: VM disk not found at: $DISK_IMG"
    echo ""
    echo "Please run ./run_qemu_vm.sh first to install Windows."
    exit 1
fi

echo "Using disk: $DISK_IMG"
echo "Creating box: $OUTPUT_BOX"
echo ""

# Create metadata.json
cat > metadata.json <<EOF
{
  "provider": "libvirt",
  "format": "qcow2",
  "virtual_size": 50
}
EOF

# Create Vagrantfile for the box
cat > Vagrantfile.box <<'EOF'
Vagrant.configure("2") do |config|
  config.vm.provider :libvirt do |libvirt|
    libvirt.driver = "kvm"
    libvirt.memory = 4096
    libvirt.cpus = 2
  end
end
EOF

# Copy the disk image
echo "Copying disk image (this may take a moment)..."
cp "$DISK_IMG" box.img

# Create the box
echo "Creating box archive..."
tar czf "$OUTPUT_BOX" metadata.json Vagrantfile.box box.img

# Clean up temporary files
rm -f metadata.json Vagrantfile.box box.img

echo ""
echo "Box created: $OUTPUT_BOX"
echo ""
echo "Add it to Vagrant with:"
echo "  vagrant box add $BOX_NAME $OUTPUT_BOX"
echo ""
echo "Then use:"
echo "  vagrant up --provider=libvirt"
