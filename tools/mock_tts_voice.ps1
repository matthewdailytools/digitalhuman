param([Parameter(Mandatory=$true)][string]$Request, [Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
$data = Get-Content -LiteralPath $Request -Raw -Encoding UTF8 | ConvertFrom-Json
$voice = New-Object -ComObject SAPI.SpVoice
$chineseVoice = @($voice.GetVoices() | Where-Object { $_.GetAttribute('Language') -match '(^|;)804(;|$)' })
if ($chineseVoice.Count -eq 0) { throw 'No Chinese Windows SAPI voice installed' }
$voice.Voice = $chineseVoice[0]
$voice.Rate = 0
$voice.Volume = 100
New-Item -ItemType Directory -Force -Path $Output | Out-Null
for ($i = 0; $i -lt $data.segments.Count; $i++) {
    $stream = New-Object -ComObject SAPI.SpFileStream
    try {
        $stream.Format.Type = 22
        $stream.Open((Join-Path $Output ('syllable_{0:D2}.wav' -f $i)), 3, $false)
        $voice.AudioOutputStream = $stream
        $voice.Speak([string]$data.segments[$i].text) | Out-Null
    } finally {
        $stream.Close()
    }
}
[pscustomobject]@{provider='mock-windows-sapi';voice=$voice.Voice.GetDescription()} | ConvertTo-Json | Set-Content (Join-Path $Output 'voice.json') -Encoding UTF8
