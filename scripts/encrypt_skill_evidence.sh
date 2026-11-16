#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 RUN_OUTPUT PUBLIC_KEY" >&2
  exit 2
fi

RUN_OUTPUT="$(cd "$1" && pwd)"
PUBLIC_KEY="$2"

[[ -d "$RUN_OUTPUT" ]] || { echo "Run output directory not found: $RUN_OUTPUT" >&2; exit 2; }
[[ -f "$PUBLIC_KEY" ]] || { echo "Recipient public key not found: $PUBLIC_KEY" >&2; exit 2; }
command -v gpg >/dev/null 2>&1 || { echo "gpg is required to encrypt experiment evidence" >&2; exit 2; }

TMP_DIR="$(mktemp -d)"
GNUPGHOME="$TMP_DIR/gnupg"
mkdir -m 700 "$GNUPGHOME"
export GNUPGHOME
trap 'rm -rf "$TMP_DIR"' EXIT

gpg --batch --import "$PUBLIC_KEY" >/dev/null 2>&1
FINGERPRINT="$(gpg --batch --with-colons --show-keys "$PUBLIC_KEY" | awk -F: '$1 == "fpr" { print $10; exit }')"
[[ -n "$FINGERPRINT" ]] || { echo "Could not read recipient fingerprint" >&2; exit 2; }

EXPECTED_FINGERPRINT="${EXPECTED_RECIPIENT_FINGERPRINT:-}"
if [[ -n "$EXPECTED_FINGERPRINT" && "$FINGERPRINT" != "$EXPECTED_FINGERPRINT" ]]; then
  echo "Recipient key fingerprint mismatch: expected $EXPECTED_FINGERPRINT, got $FINGERPRINT" >&2
  exit 2
fi

mkdir -p "$RUN_OUTPUT/encrypted"

encrypt_paths() {
  local archive_name="$1"
  shift
  local archive="$TMP_DIR/${archive_name}.tar.gz"
  local ciphertext="$RUN_OUTPUT/encrypted/${archive_name}.tar.gz.gpg"
  local -a paths=("$@")

  (("${#paths[@]}" > 0)) || return 0
  tar -czf "$archive" -C "$RUN_OUTPUT" -- "${paths[@]}"
  gpg --batch --yes --trust-model always \
    --recipient "$FINGERPRINT" \
    --output "$ciphertext" \
    --encrypt "$archive"
  rm -f "$archive"
  echo "Encrypted ${#paths[@]} path(s): $ciphertext"
}

shopt -s nullglob
scorer_paths=()
private_paths=()
[[ -f "$RUN_OUTPUT/index.json" ]] && private_paths+=("index.json")

for skill_dir in "$RUN_OUTPUT"/*/; do
  [[ -d "$skill_dir" ]] || continue
  skill_name="$(basename "$skill_dir")"
  if [[ -f "$skill_dir/scorer/scoring-packet.json" ]]; then
    scorer_paths+=("$skill_name/scorer")
  fi
  [[ -d "$skill_dir/controller" ]] && private_paths+=("$skill_name/controller")
  [[ -d "$skill_dir/experiment" ]] && private_paths+=("$skill_name/experiment")
done

encrypt_paths "scorer-packets" "${scorer_paths[@]}"
encrypt_paths "controller-and-evidence" "${private_paths[@]}"

if [[ ! -f "$RUN_OUTPUT/encrypted/scorer-packets.tar.gz.gpg" && ! -f "$RUN_OUTPUT/encrypted/controller-and-evidence.tar.gz.gpg" ]]; then
  echo "No scorer or controller evidence was available to encrypt."
fi
