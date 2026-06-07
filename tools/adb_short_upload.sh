#!/usr/bin/env bash
# ADB YouTube Shorts upload — deterministic tap scenario for Pixel 1080x2400.
# Splits the flow into stages so the two VARIABLE steps (channel switch +
# gallery video pick) stay vision-driven, while the rest is fixed coordinates.
#
# Validated coords (1080x2400, YouTube app 2026-05). The status bar is included
# in both screencap and `input tap`, so no offset is applied.
#
# Usage:
#   adb_short_upload.sh push      <mp4>                 # push video + media scan
#   adb_short_upload.sh open                            # Create(+) -> Short -> gallery
#   adb_short_upload.sh pick      <x> <y>               # tap the target thumbnail (vision-found)
#   adb_short_upload.sh edit                            # Next -> trim Done -> Kaiju 10% -> Next
#   adb_short_upload.sh details   "<title>"             # title + not-for-kids + Upload Short
#   adb_short_upload.sh shot      [outfile]             # screencap -> resized PNG for vision
set -uo pipefail

GBOARD="com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME"
ADBKBD="com.android.adbkeyboard/.AdbIME"
t(){ adb shell input tap "$1" "$2"; sleep "${3:-1.5}"; }

case "${1:-}" in
  push)
    f="/sdcard/Movies/$(basename "$2")"
    adb push "$2" "$f" >/dev/null
    adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://$f" >/dev/null
    echo "pushed $f" ;;

  open)
    t 690 2260 3          # Create (+)
    t 180 1840 3 ;;       # gallery "Add"

  pick)                   # $2=x $3=y  (vision-found thumbnail center)
    t "$2" "$3" 2
    t 840 2235 3 ;;       # Next

  edit)
    t 540 700 1; t 869 2224 3      # pause preview, then trim Done
    t 540 200 3                    # Add sound
    t 540 340 2                    # search field
    adb shell input text "Kaiju"; sleep 1
    adb shell input keyevent 66; sleep 3   # enter
    t 250 680 2                    # first result (Kaiju by sakanaction)
    t 962 672 3                    # blue arrow -> use sound
    t 1000 215 2                   # volume icon
    adb shell input swipe 985 2265 135 2265 700; sleep 1   # music -> ~10%
    t 1000 1790 2                  # confirm volume (check mark)
    t 840 2212 3 ;;                # Next -> details

  details)                # $2=title
    adb shell ime set "$GBOARD" >/dev/null; sleep 1
    t 454 560 2                    # caption field (Gboard focus established)
    adb shell ime set "$ADBKBD" >/dev/null; sleep 1
    adb shell am broadcast -a ADB_INPUT_TEXT --es msg "$2" >/dev/null; sleep 2
    adb shell input keyevent 4; sleep 2     # dismiss keyboard
    t 300 1250 2                    # Select audience
    t 250 888 1                     # No, not made for kids
    t 82 194 2                      # back
    t 842 2250 4 ;;                 # Upload Short

  shot)
    out="${2:-/tmp/now.png}"
    adb exec-out screencap -p > "$out"
    sips --resampleHeight 1900 "$out" --out "${out%.png}_h.png" >/dev/null 2>&1
    echo "${out%.png}_h.png" ;;

  *) echo "usage: $0 {push|open|pick|edit|details|shot} ..." >&2; exit 2 ;;
esac
