#!/usr/bin/env bash
set -euo pipefail

stage="$PWD/build/windows"
sources="$stage/sources"
prefix="$stage/x264-install"
mkdir -p "$sources" "$stage/dependencies/bin"

download() {
    local url="$1" file="$2" sha256="$3"
    curl --fail --location --silent --show-error --retry 3 "$url" --output "$file"
    printf '%s  %s\n' "$sha256" "$file" | sha256sum --check -
}

ffmpeg=8.1.2
x264=b35605ace3ddf7c1a5d67a2eb553f034aef41d55
download "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n$ffmpeg" \
    "$sources/ffmpeg-n$ffmpeg.tar.gz" 9fd092511605bbebafe095ea6d38d9e40f34d12f7386e1258372df8be0576eb7
download "https://code.videolan.org/videolan/x264/-/archive/$x264/x264-$x264.tar.gz" \
    "$sources/x264-$x264.tar.gz" cd71a7515b0e9a012e1ac9b1f8415bebcaf6fc97d4db32286642ac4c0fbe24f9

tar -xzf "$sources/x264-$x264.tar.gz" -C "$stage"
(
    cd "$stage/x264-$x264"
    ./configure --prefix="$prefix" --enable-static --disable-cli --disable-opencl
    make -j4
    make install
)

tar -xzf "$sources/ffmpeg-n$ffmpeg.tar.gz" -C "$stage"
(
    cd "$stage/FFmpeg-n$ffmpeg"
    export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
    ./configure --target-os=mingw32 --arch=x86_64 --enable-gpl --enable-libx264 \
        --disable-autodetect --disable-doc --disable-debug --disable-ffplay \
        --pkg-config-flags=--static --extra-ldflags=-static
    make -j4
    cp ffmpeg.exe ffprobe.exe "$stage/dependencies/bin/"
    ./ffmpeg.exe -version > "$sources/FFmpeg-build.txt"
    cp COPYING.GPLv2 COPYING.GPLv3 COPYING.LGPLv2.1 COPYING.LGPLv3 "$sources/"
)
cp "$stage/x264-$x264/COPYING" "$sources/x264-COPYING"
gcc --version > "$sources/compiler.txt"
for binary in "$stage/dependencies/bin/"*.exe; do
    objdump -p "$binary" | awk '/DLL Name:/ { print $NF }' | tee -a "$sources/FFmpeg-imports.txt"
    if grep -Eiq '(^msys-|^lib).*\.dll$' "$sources/FFmpeg-imports.txt"; then
        echo "FFmpeg has an unexpected non-system DLL dependency" >&2
        exit 1
    fi
done
