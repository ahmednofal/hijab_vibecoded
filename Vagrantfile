# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  # We'll create a box from the Windows 11 ISO you have
  # For now, this uses a manual VM creation approach with libvirt
  config.vm.box = "windows11-hijab"
  config.vm.box_check_update = false
  
  # Use libvirt provider (works with QEMU/KVM)
  config.vm.provider "libvirt" do |libvirt|
    libvirt.memory = 4096
    libvirt.cpus = 2
    libvirt.graphics_type = "spice"
    libvirt.video_type = "qxl"
    libvirt.driver = "kvm"
  end

  # Share the current project folder with the VM
  # Note: libvirt uses 9p for folder sharing (different from VirtualBox)
  config.vm.synced_folder ".", "/vagrant", type: "9p", disabled: false, 
    accessmode: "mapped"

  # For Windows, if you create a box later:
  # config.vm.communicator = "winrm"
  # config.winrm.username = "vagrant"
  # config.winrm.password = "vagrant"
end
