param([Parameter(Mandatory=$true)][string]$InputDirectory, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($operation, $resultType) {
    $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
    try { $task.Wait() } catch { throw $task.Exception.ToString() }
    return $task.Result
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
foreach ($item in Get-ChildItem -LiteralPath $InputDirectory -Filter '*.png' -File) {
    # Ordinary read-only file access; no WinRT Storage broker permission needed.
    $fileStream = [IO.File]::OpenRead($item.FullName)
    $stream = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($fileStream)
    try {
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $ocr = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $lines = @(); $index = 0
            foreach ($line in $ocr.Lines) {
                $words = @()
                foreach ($word in $line.Words) {
                    $r = $word.BoundingRect
                    $words += @{text=$word.Text; bbox=@($r.X,$r.Y,$r.Width,$r.Height)}
                }
                $lines += @{id="ocr-$index"; text=$line.Text; words=$words}
                $index++
            }
            $result = @{source_path=$item.FullName; source_sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash; width=$bitmap.PixelWidth; height=$bitmap.PixelHeight; engine='Windows.Media.Ocr'; language='en-US'; windows_version=[Environment]::OSVersion.Version.ToString(); coordinate_space='original image pixels; no transformations'; text_angle=$ocr.TextAngle; text=$ocr.Text; lines=$lines}
            $path = Join-Path $OutputDirectory ($item.BaseName + '.ocr.json')
            [IO.File]::WriteAllText($path, ($result | ConvertTo-Json -Depth 15), [Text.UTF8Encoding]::new($false))
            Write-Output "$($item.Name): $($lines.Count) OCR lines"
        } finally { $bitmap.Dispose() }
    } finally { $stream.Dispose(); $fileStream.Dispose() }
}
