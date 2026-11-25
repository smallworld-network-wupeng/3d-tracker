#!/bin/zsh
set -euo pipefail

project_dir=${0:A:h:h}
cd "$project_dir"

if [[ $# != 1 || ! -x "$1/Contents/MacOS/Chromium" ]]; then
  print -u2 "Usage: $0 /path/to/Chromium.app"
  exit 1
fi
chromium_source=${1:A}
chromium_version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$chromium_source/Contents/Info.plist")
if [[ "$chromium_version" != 157.0.8103.78 ]]; then
  print -u2 "Update the pinned Chromium version and its source references before building."
  exit 1
fi

python_bin="$project_dir/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  print -u2 "Missing .venv. Create it and install requirements first."
  exit 1
fi

export PYINSTALLER_CONFIG_DIR="$project_dir/build/pyinstaller-cache"
mkdir -p build
stage=$(mktemp -d "$project_dir/build/macos-release.XXXXXXXX")
export TRACKER_MACOS_DEPENDENCIES="$stage/dependencies"
"$python_bin" packaging/prepare_macos_dependencies.py "$TRACKER_MACOS_DEPENDENCIES"

chromium="$stage/Chromium.app"
cp -R -P "$chromium_source" "$chromium"
xattr -cr "$chromium"
codesign --force --deep --sign - "$chromium"
node packaging/extract_chromium_credits.mjs \
  "$chromium/Contents/Frameworks/Chromium Framework.framework/Resources/resources.pak" \
  "$TRACKER_MACOS_DEPENDENCIES/third-party/Chromium-credits.html"

"$python_bin" -m PyInstaller --noconfirm --clean packaging/macos.spec

app="$project_dir/dist/3D Tracker.app"
mkdir -p "$app/Contents/Resources/chromium"
mv "$chromium" "$app/Contents/Resources/chromium/Chromium.app"
ln -s ../Resources/chromium "$app/Contents/Frameworks/chromium"
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict "$app"
codesign --verify --deep --strict "$app/Contents/Resources/chromium/Chromium.app"

mkdir -p release/github
archive="$project_dir/release/github/3D-Tracker-0.1.0-macOS-arm64.zip"
ditto -c -k --sequesterRsrc --keepParent "$app" "$stage/app.zip"
mv -f "$stage/app.zip" "$archive"

du -sh "$app" "$archive"
print "Built: $app"
print "Archive: $archive"
