# Launcher for Neo4j cypher-shell (the Neo4j terminal CLI).
# Usage:
#   .\cypher.ps1                 -> opens interactive shell connected to your Aura DB
#   .\cypher.ps1 --version       -> any extra args are passed straight to cypher-shell
#
# Credentials are loaded automatically from aura_credentials.txt.

# Point to the Java 21 that cypher-shell needs
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

# Load NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD from the credentials file
$credsFile = Join-Path $PSScriptRoot "aura_credentials.txt"
if (Test-Path $credsFile) {
    Get-Content $credsFile | ForEach-Object {
        if ($_ -match '^\s*([^=#]+)=(.*)$') {
            Set-Item -Path "env:$($Matches[1].Trim())" -Value $Matches[2].Trim()
        }
    }
}

$shell = Join-Path $PSScriptRoot "tools\cypher-shell-2026.09.0\bin\cypher-shell.bat"

$uri  = if ($env:NEO4J_URI)      { $env:NEO4J_URI }      else { "neo4j+s://319896c3.databases.neo4j.io" }
$user = if ($env:NEO4J_USERNAME) { $env:NEO4J_USERNAME } else { "319896c3" }
$db   = if ($env:NEO4J_DATABASE) { $env:NEO4J_DATABASE } else { "319896c3" }

if ($args.Count -gt 0) {
    & $shell -a $uri -u $user -d $db @args
} else {
    # Password comes from NEO4J_PASSWORD (read by cypher-shell itself, never typed in the command)
    & $shell -a $uri -u $user -d $db
}
