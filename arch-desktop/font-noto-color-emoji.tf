# Color-emoji font. starship's default module symbols are emoji (e.g. the terraform
# module's 💠 = U+1F4A0), and no other installed font covers those codepoints, so
# without this they render as tofu in the prompt. Also covers the other default
# emoji symbols (🦀 rust, 🐍 python, ☁️ aws, ...).
resource "host_package_pacman" "font_noto_color_emoji" {
  name = "noto-fonts-emoji"
}
