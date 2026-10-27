# Builds the app and the developer checks into dist\ (requires the .NET 8 runtime to run).
$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$root = Split-Path $PSScriptRoot -Parent
# Uses a repository-local SDK in .tools\dotnet when present, otherwise the installed one.
$dotnet = Join-Path $root '.tools\dotnet\dotnet.exe'
if (!(Test-Path $dotnet)) { $dotnet = 'dotnet' }
foreach ($project in 'src\YiQu\YiQu.csproj', 'src\YiQu.Cli\YiQu.Cli.csproj') {
    & $dotnet publish (Join-Path $root $project) -c Release -r win-x64 --self-contained false -o (Join-Path $root 'dist')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
