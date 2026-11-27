param(
    [Parameter(Mandatory)]
    [ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$Tag
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$stage = Join-Path $root 'build/windows'
$dependencies = Join-Path $stage 'dependencies'
$sources = Join-Path $stage 'sources'
$notices = Join-Path $dependencies 'third-party'
New-Item -ItemType Directory -Force $notices | Out-Null

$chromiumVersion = '158.0.8127.36-1.1'
$chromiumRepo = 'https://github.com/ungoogled-software/ungoogled-chromium-windows'
$chromiumName = "ungoogled-chromium_${chromiumVersion}_windows_x64.zip"
$chromiumZip = Join-Path $stage $chromiumName
curl.exe --fail --location --silent --show-error --retry 3 "$chromiumRepo/releases/download/$chromiumVersion/$chromiumName" -o $chromiumZip
if ((Get-FileHash $chromiumZip -Algorithm SHA256).Hash -ne 'bc78b9590881f8ca99aca29288d1b347ffdd689ca8a57384bb0bc113ef687b6b') {
    throw 'Chromium download does not match the pinned SHA-256.'
}
$chromiumUnpacked = Join-Path $stage 'chromium-unpacked'
Expand-Archive -LiteralPath $chromiumZip -DestinationPath $chromiumUnpacked -Force
$chromium = @(Get-ChildItem $chromiumUnpacked -Recurse -Filter chrome.exe -File)
if ($chromium.Count -ne 1) { throw 'Expected exactly one Chromium executable in the upstream archive.' }
Copy-Item -LiteralPath $chromium[0].DirectoryName -Destination (Join-Path $dependencies 'chromium') -Recurse
node packaging/extract_chromium_credits.mjs (Join-Path $dependencies 'chromium/resources.pak') (Join-Path $notices 'Chromium-credits.html')

$pythonVersion = python -c 'import platform; print(platform.python_version())'
$cesiumVersion = node -p 'require("./node_modules/cesium/package.json").version'
$pythonLicense = python -c 'import pathlib, sys; print(pathlib.Path(sys.base_prefix) / "LICENSE.txt")'
if (Test-Path -LiteralPath $pythonLicense) {
    Copy-Item -LiteralPath $pythonLicense -Destination (Join-Path $notices 'Python-LICENSE.txt')
} else {
    curl.exe --fail --location --silent --show-error --retry 3 "https://raw.githubusercontent.com/python/cpython/v$pythonVersion/LICENSE" -o (Join-Path $notices 'Python-LICENSE.txt')
}
Copy-Item node_modules/cesium/LICENSE.md (Join-Path $notices 'Cesium-LICENSE.md')
$sitePackages = python -c 'import sysconfig; print(sysconfig.get_path("purelib"))'
foreach ($name in @('fitdecode-0.11.0', 'pyinstaller-6.22.3')) {
    Copy-Item (Join-Path $sitePackages "$name.dist-info/licenses") (Join-Path $notices $name) -Recurse
}
Get-ChildItem $sitePackages -Directory -Filter '*.dist-info' | Where-Object {
    $_.Name -match '^(pillow-|pillow_heif-|tzdata-)'
} | ForEach-Object {
    $licenseFiles = @(Get-ChildItem $_.FullName -Recurse -File | Where-Object {
        $_.Name -match '^(license|copying|notice)' -or $_.Directory.Name -eq 'licenses'
    })
    if ($licenseFiles) {
        $destination = Join-Path $notices $_.BaseName
        New-Item -ItemType Directory -Force $destination | Out-Null
        $licenseFiles | Copy-Item -Destination $destination
    }
}
Copy-Item (Join-Path $sources 'COPYING.*'), (Join-Path $sources 'x264-COPYING'), (Join-Path $sources 'FFmpeg-build.txt') $notices

@"
# Third-party software

3D Tracker uses the MIT license. Its bundled dependencies retain their own licenses.
You may replace the dynamically linked LGPL components with compatible modified
builds and reverse engineer the application as needed to debug those changes.

- Chromium $chromiumVersion build and patches: $chromiumRepo/tree/$chromiumVersion
- Chromium upstream source: https://chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8127.36
- Chromium third-party notices: Chromium-credits.html
- FFmpeg 8.1.2 and x264 are built from the archives in the matching Windows third-party source ZIP. See FFmpeg-build.txt and the root scripts/build_windows_ffmpeg.sh for the build recipe.
- PySide6 and Shiboken 6.10.3 (LGPL-3.0): https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.3-src/
- Qt 6.10.3 (LGPL-3.0 and third-party terms): https://download.qt.io/archive/qt/6.10/6.10.3/submodules/
- Qt Multimedia FFmpeg source: https://ffmpeg.org/releases/ffmpeg-7.1.3.tar.xz
- Python ${pythonVersion}: https://www.python.org/ftp/python/${pythonVersion}/
- Fitdecode 0.11.0 (MIT): https://pypi.org/project/fitdecode/0.11.0/#files
- Pillow 11.3.0 (MIT-CMU): https://pypi.org/project/Pillow/11.3.0/#files
- pillow-heif 1.1.1 and its bundled libraries: https://github.com/bigcat88/pillow_heif/tree/v1.1.1
- IANA timezone data for Windows: https://pypi.org/project/tzdata/
- PyInstaller 6.22.3 (GPL with bootloader exception): https://github.com/pyinstaller/pyinstaller/tree/v6.22.3
- CesiumJS ${cesiumVersion} (Apache-2.0 and third-party terms): https://github.com/CesiumGS/cesium/tree/${cesiumVersion}
"@ | Set-Content -LiteralPath (Join-Path $notices 'SOURCE.md') -Encoding utf8

$env:TRACKER_WINDOWS_DEPENDENCIES = $dependencies
python -m PyInstaller --noconfirm --clean --workpath build/pyinstaller-windows packaging/windows.spec
$app = Join-Path $root 'dist/3D Tracker'
$examples = Join-Path $app 'examples'
New-Item -ItemType Directory -Force $examples | Out-Null
Copy-Item examples/synthetic-track.kml $examples

$out = Join-Path $root 'release/windows'
New-Item -ItemType Directory -Force $out | Out-Null
$version = $Tag.Substring(1)
$appZip = Join-Path $out "3D-Tracker-$version-windows-x64.zip"
$sourceZip = Join-Path $out "3D-Tracker-$version-windows-third-party-source.zip"
tar.exe -a -c -f $appZip -C (Split-Path $app) (Split-Path $app -Leaf)
Copy-Item $notices (Join-Path $sources 'third-party') -Recurse
Copy-Item scripts/build_windows_ffmpeg.sh $sources
Compress-Archive -Path (Join-Path $sources '*') -DestinationPath $sourceZip -CompressionLevel Optimal -Force
Get-FileHash -Algorithm SHA256 $appZip, $sourceZip | Format-List
