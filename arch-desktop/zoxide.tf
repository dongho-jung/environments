resource "host_package_pacman" "zoxide" {
  name = "zoxide"
}

resource "host_file_block" "zoxide_init" {
  block = host_file.zshrc.blocks.init

  content = <<-EOT
    eval "$(zoxide init zsh)"

    # Keep zoxide's ranked lookup as the fast path. If it finds nothing, retry
    # against path components with bounded approximate matching so common typos
    # such as `bcakend` still resolve to `backend`.
    function __zoxide_fuzzy_query() {
      emulate -L zsh
      setopt extended_glob

      local -a queries candidates path_components components corrections
      local query candidate component tokenized correction fallback_candidate ranked_candidate pattern
      local query_length max_errors errors

      queries=("$@")
      for query in "$${queries[@]}"; do
        [[ $query != -* && $query != */* ]] || return 1
        query_length=$${#query}
        (( query_length >= 3 )) || return 1
      done

      candidates=("$${(@f)$(command zoxide query --list --exclude "$(__zoxide_pwd)" 2>/dev/null)}")
      (( $${#candidates} > 0 )) || return 1

      for query in "$${queries[@]}"; do
        query_length=$${#query}
        (( max_errors = query_length < 7 ? 1 : 3 ))
        correction=

        for (( errors = 0; errors <= max_errors; ++errors )); do
          pattern="(#ia$errors)$${(b)query}"

          for candidate in "$${candidates[@]}"; do
            path_components=("$${(@s:/:)candidate}")
            components=("$${path_components[@]}")
            for component in "$${path_components[@]}"; do
              tokenized=$${component//[-_.]/ }
              components+=("$${(@s: :)tokenized}")
            done

            for component in "$${components[@]}"; do
              if [[ -n $component && $component == $${~pattern} ]]; then
                correction=$component
                fallback_candidate=$candidate
                break 3
              fi
            done
          done
        done

        [[ -n $correction ]] || return 1
        corrections+=("$correction")
      done

      ranked_candidate="$(command zoxide query --exclude "$(__zoxide_pwd)" -- "$${corrections[@]}" 2>/dev/null)" || {
        (( $${#queries} == 1 )) || return 1
        ranked_candidate=$fallback_candidate
      }
      print -r -u2 -- "zoxide: corrected '$${(j: :)queries}' -> '$${(j: :)corrections}'"
      print -r -- "$ranked_candidate"
    }

    function z() {
      __zoxide_z "$@" 2>/dev/null && return

      local result
      result="$(__zoxide_fuzzy_query "$@")" && __zoxide_cd "$result" && return

      __zoxide_z "$@"
    }
  EOT
}
