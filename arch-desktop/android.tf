# CertMind uses Android Gradle Plugin 8.10: JDK 17, Build Tools 35.0.0,
# and API 36 are its supported/default toolchain versions.
resource "host_package_pacman" "jdk17_openjdk" {
  name = "jdk17-openjdk"
}

# Keep physical-device debugging available alongside the emulator.
resource "host_package_pacman" "android_udev" {
  name = "android-udev"
}

# Reviewed 2026-08-24: these AUR packages unpack checksum-pinned Google SDK
# artifacts under /opt/android-sdk and install only their package metadata,
# profile snippets, licenses, and (for platform-tools) the optional adb unit.
resource "host_package_aur" "android_sdk_cmdline_tools" {
  name = "android-sdk-cmdline-tools-latest"

  depends_on = [
    host_package_pacman.jdk17_openjdk,
  ]
}

resource "host_package_aur" "android_sdk_platform_tools" {
  name = "android-sdk-platform-tools"

  depends_on = [
    host_package_pacman.android_udev,
    host_package_aur.android_sdk_cmdline_tools,
  ]
}

resource "host_package_aur" "android_sdk_build_tools_35" {
  name = "android-sdk-build-tools-35"

  depends_on = [
    host_package_aur.android_sdk_platform_tools,
  ]
}

resource "host_package_aur" "android_platform_35" {
  name = "android-platform-35"

  depends_on = [
    host_package_aur.android_sdk_build_tools_35,
  ]
}

resource "host_package_aur" "android_platform_36" {
  name = "android-platform-36"

  depends_on = [
    host_package_aur.android_platform_35,
  ]
}

resource "host_package_aur" "android_emulator" {
  name = "android-emulator"

  depends_on = [
    host_package_aur.android_platform_36,
  ]
}

resource "host_package_aur" "android_api36_google_apis_system_image" {
  name = "android-google-apis-x86-64-system-image"

  depends_on = [
    host_package_aur.android_emulator,
  ]
}

resource "host_file_block" "android_environment" {
  block   = host_file.zshrc.blocks.environment
  content = <<-EOT
    export JAVA_HOME="/usr/lib/jvm/java-17-openjdk"
    export ANDROID_HOME="/opt/android-sdk"
  EOT

  depends_on = [
    host_package_pacman.jdk17_openjdk,
    host_package_aur.android_sdk_cmdline_tools,
  ]
}

resource "host_file_block" "android_path" {
  block   = host_file.zshrc.blocks.path
  content = "export PATH=\"$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH\""

  depends_on = [
    host_file_block.android_environment,
    host_package_aur.android_api36_google_apis_system_image,
  ]
}
