$ErrorActionPreference = 'Stop'
# Builds release\YiQu-Setup-<version>.exe: self-contained app (no .NET install needed) packed with Inno Setup.
# Only program files are staged; user settings, API keys and history stay in %LOCALAPPDATA%\YiQu.
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$root = Split-Path $PSScriptRoot -Parent
# Uses a repository-local SDK in .tools\dotnet when present, otherwise the installed one.
$dotnet = Join-Path $root '.tools\dotnet\dotnet.exe'
if (!(Test-Path $dotnet)) { $dotnet = 'dotnet' }
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (!$iscc) { throw 'Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup' }

$project = Join-Path $root 'src\YiQu\YiQu.csproj'
$version = ([xml](Get-Content $project -Raw)).Project.PropertyGroup.Version | Where-Object { $_ } | Select-Object -First 1
if (!$version) { throw 'Version missing in YiQu.csproj' }
$stage = Join-Path $root ('build\installer\app-' + [Guid]::NewGuid().ToString('N'))

& $dotnet publish $project -c Release -r win-x64 --self-contained true -o $stage -p:DebugType=None -p:DebugSymbols=false
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Refuse to package anything that looks like user data or configuration.
$unexpected = Get-ChildItem $stage -Recurse -File | Where-Object { $_.Name -match '^(settings|history).*\.json$' -or $_.Extension -in '.lnk', '.env', '.key' }
if ($unexpected) { throw "Unexpected files in package: $($unexpected.FullName -join ', ')" }

& $iscc "/DAppVersion=$version" "/DSourceDir=$stage" (Join-Path $root 'installer\YiQu.iss')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-Item (Join-Path $root "release\YiQu-Setup-$version.exe")
