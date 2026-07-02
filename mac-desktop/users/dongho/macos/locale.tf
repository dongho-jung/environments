resource "host_macos_default" "languages" {
  domain      = "NSGlobalDomain"
  key         = "AppleLanguages"
  string_list = ["en-JP", "ja-JP", "ko-JP"]
}

resource "host_macos_default" "locale" {
  domain = "NSGlobalDomain"
  key    = "AppleLocale"
  string = "en_JP"
}
