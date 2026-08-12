# The TP-Link UB500 is supported by the in-kernel btusb/btrtl drivers and this
# Realtek firmware payload. BlueZ supplies the system D-Bus service that turns
# the detected hci0 controller into a usable Bluetooth adapter.
resource "host_package_pacman" "linux_firmware_realtek" {
  name = "linux-firmware-realtek"
}

resource "host_package_pacman" "bluez" {
  name = "bluez"

  depends_on = [
    host_package_pacman.linux_firmware_realtek,
  ]
}

# bluetoothctl is useful for diagnostics and as a fallback pairing interface.
resource "host_package_pacman" "bluez_utils" {
  name = "bluez-utils"

  depends_on = [
    host_package_pacman.bluez,
  ]
}

# Waybar opens this GTK manager for pairing, trusting, reconnecting, and
# removing devices. The applet is intentionally not autostarted because the
# native Waybar Bluetooth module provides the persistent status UI.
resource "host_package_pacman" "blueman" {
  name = "blueman"

  depends_on = [
    host_package_pacman.bluez_utils,
  ]
}

resource "host_systemd_service" "bluetooth" {
  name    = "bluetooth.service"
  enabled = true
  running = true

  depends_on = [
    host_package_pacman.bluez,
  ]
}
