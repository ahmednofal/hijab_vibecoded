# QEMU VM Setup for Windows Testing

Since VirtualBox doesn't work with kernel 6.15, we're using QEMU/KVM instead.

## Why QEMU?

✅ Works with newer kernels (including 6.15+)
✅ No kernel module compilation needed
✅ Faster than VirtualBox in many cases
✅ Built-in shared folder support
✅ Simpler, lighter weight

## Quick Start

### 1. First Time: Install Windows

Run the installation script:
```bash
./run_qemu_vm.sh
```

This will:
- Create a 50GB virtual disk
- Boot from your Windows 11 ISO
- Start the VM in a window

**Install Windows:**
1. Follow Windows 11 setup (skip Microsoft account if you can)
2. Username: `vagrant` Password: `vagrant` (or your choice)
3. Install normally
4. Shut down Windows when done

### 2. After Installation: Run Windows

```bash
./run_qemu_vm_installed.sh
```

This boots directly to Windows (no ISO).

### 3. Access Your Project in Windows

Your project folder is shared via SMB.

**In Windows:**
1. Open File Explorer
2. In address bar, type: `\\10.0.2.4\qemu`
3. Browse to your project
4. Or map as network drive (Z:) for easier access

## VM Controls

| Key Combination | Action |
|----------------|---------|
| `Ctrl+Alt+G` | Release mouse/keyboard from VM |
| `Ctrl+Alt+F` | Toggle fullscreen |
| `Ctrl+Alt+Q` | Quit VM |

## Testing Your Python App in the VM

Once Windows is running:

1. Map network drive:
   ```
   net use Z: \\10.0.2.4\qemu
   ```

2. Navigate to project:
   ```cmd
   cd Z:\
   ```

3. Run setup:
   ```cmd
   setup_windows.bat
   ```

4. Run application:
   ```cmd
   run_windows.bat
   ```

## Files

- `run_qemu_vm.sh` - First boot with ISO (install Windows)
- `run_qemu_vm_installed.sh` - Normal boot (use after installing)
- VM disk location: `~/.local/share/qemu/windows11-hijab.qcow2`

## Troubleshooting

### VM won't start
- Check KVM is enabled: `kvm-ok`
- If "KVM not available", your CPU doesn't support virtualization or it's disabled in BIOS

### Shared folder not accessible
- Windows may need to enable SMB1:
  - Control Panel → Programs → Turn Windows features on/off
  - Enable "SMB 1.0/CIFS File Sharing Support"

### VM is slow
- Make sure you see "KVM acceleration is active" when VM starts
- If not, your system doesn't support KVM (will fall back to emulation, which is slow)

## Compared to Vagrant

| Feature | QEMU (This) | Vagrant + VirtualBox |
|---------|-------------|---------------------|
| Kernel 6.15 | ✅ Works | ❌ Broken |
| Setup | Manual install once | Automated (if box available) |
| Shared folders | SMB | VirtualBox Guest Additions |
| Management | Simple scripts | `vagrant up/down/destroy` |
| Disk space | ~20GB after install | Similar |

## Alternative: Vagrant with Libvirt

If you want to use Vagrant with QEMU/KVM (instead of raw QEMU):

```bash
vagrant plugin install vagrant-libvirt
# Update Vagrantfile to use libvirt provider
```

But for quick testing, the simple QEMU scripts above are easier.
