param(
    [Parameter(Mandatory)]
    [ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$Tag
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$version = $Tag.Substring(1)
$archive = (Resolve-Path "release/windows/3D-Tracker-$version-windows-x64.zip").Path
$testRoot = Join-Path $env:RUNNER_TEMP "tracker test $([guid]::NewGuid())"
$work = Join-Path $testRoot '工作目录'
$app = Join-Path $testRoot '3D Tracker'
New-Item -ItemType Directory -Path $work | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $testRoot

$config = Get-Content -LiteralPath 'examples/video_project.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$config.track.file = Join-Path $app 'examples/synthetic-track.kml'
$config.render.output = Join-Path $work '路线演示.mp4'
$configPath = Join-Path $work '示例项目.json'
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding utf8

$env:THREED_TRACKER_WORK_ROOT = $work
$env:THREED_TRACKER_SOFTWARE_WEBGL = '1'
$env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
$exe = Join-Path $app '3D Tracker.exe'
$gui = Start-Process -FilePath $exe -WorkingDirectory $work -PassThru
try {
    if ($gui.WaitForExit(4000)) {
        throw "The extracted application exited unexpectedly (code $($gui.ExitCode))."
    }
} finally {
    if (!$gui.HasExited) { $gui.Kill() }
}

$worker = Join-Path $app '3D Tracker Worker.exe'
& $worker --generate-from-config $configPath
$ffprobe = Join-Path $app '_internal/bin/ffprobe.exe'
$probe = & $ffprobe -v error -count_frames -select_streams 'v:0' -show_entries 'stream=codec_name,width,height,nb_read_frames:format=duration' -of json $config.render.output |
    ConvertFrom-Json
$video = $probe.streams[0]
if ($video.codec_name -ne 'h264' -or $video.width -ne 1280 -or $video.height -ne 720 -or [int]$video.nb_read_frames -ne 60 -or [double]$probe.format.duration -ne 4.0) {
    throw "Unexpected MP4: $($probe | ConvertTo-Json -Depth 6 -Compress)"
}
Write-Host 'Verified the Windows GUI starts and the extracted app exports a 4-second, 60-frame, 1280 x 720 H.264 MP4 using its bundled tools.'
