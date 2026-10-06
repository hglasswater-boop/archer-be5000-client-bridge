# Temporary PC Ethernet addressing for the isolated BE5000 management network.
# No router configuration, Wi-Fi adapter, firewall, or credential changes.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Pin', 'RestoreDhcp')]
    [string]$Mode,
    [Parameter(Mandatory=$true)]
    [ValidateRange(1,65535)]
    [int]$InterfaceIndex,
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[0-9A-Fa-f]{2}(-[0-9A-Fa-f]{2}){5}$')]
    [string]$ExpectedRouterMac,
    [ValidatePattern('^192\.168\.1\.(?:[2-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-4])$')]
    [string]$CurrentAddress
)
$ErrorActionPreference = 'Stop'
$managementAddress = '192.168.1.1'
$pinnedAddress = '192.168.1.52'
$evidenceDirectory = Join-Path (Split-Path $PSScriptRoot -Parent) 'local-evidence'
New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
$resultPath = Join-Path $evidenceDirectory ('wired-management-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json')
$result = [ordered]@{mode=$Mode; interface_index=$InterfaceIndex; outcome='stopped'; captured_at=[DateTime]::UtcNow.ToString('o')}
$changed = $false
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator rights are required to change the PC Ethernet address.'
    }
    $adapter = @(Get-NetAdapter | Where-Object ifIndex -eq $InterfaceIndex)
    if ($adapter.Count -ne 1 -or [string]$adapter[0].MediaType -ne '802.3' -or [string]$adapter[0].Status -ne 'Up') {
        throw 'The selected interface must be a single connected Ethernet adapter.'
    }
    $addresses = @(Get-NetIPAddress -InterfaceIndex $InterfaceIndex -AddressFamily IPv4)
    $ipInterface = Get-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4
    $result.before = @{dhcp=[string]$ipInterface.Dhcp; addresses=@($addresses | Select-Object IPAddress,PrefixLength,PrefixOrigin); adapter=$adapter[0].Name}
    if ($Mode -eq 'Pin') {
        if (-not $CurrentAddress -or $addresses.Count -ne 1 -or $addresses[0].IPAddress -ne $CurrentAddress -or
            $addresses[0].PrefixLength -ne 24 -or [string]$addresses[0].PrefixOrigin -ne 'Dhcp' -or
            [string]$ipInterface.Dhcp -ne 'Enabled') {
            throw 'The Ethernet DHCP baseline has changed; no address changes were made.'
        }
        $probe = [System.Net.NetworkInformation.Ping]::new()
        try { $reply = $probe.Send($managementAddress,1500) } finally { $probe.Dispose() }
        $neighbor = @(Get-NetNeighbor -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 | Where-Object IPAddress -eq $managementAddress)
        if ([string]$reply.Status -ne 'Success' -or $neighbor.Count -ne 1 -or $neighbor[0].LinkLayerAddress -ine $ExpectedRouterMac) {
            throw 'The directly connected router identity was not verified.'
        }
        $changed = $true
        Set-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 -Dhcp Disabled -PolicyStore ActiveStore
        New-NetIPAddress -InterfaceIndex $InterfaceIndex -IPAddress $pinnedAddress -PrefixLength 24 -PolicyStore ActiveStore | Out-Null
        $ready = $false
        for ($attempt=0; $attempt -lt 20; $attempt++) {
            $pin = Get-NetIPAddress -InterfaceIndex $InterfaceIndex -IPAddress $pinnedAddress -ErrorAction SilentlyContinue
            if ($pin -and [string]$pin.AddressState -eq 'Preferred') { $ready=$true; break }
            if ($pin -and [string]$pin.AddressState -eq 'Duplicate') { break }
            Start-Sleep -Milliseconds 500
        }
        $result.pin_state = @{dhcp=[string](Get-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4).Dhcp;
            addresses=@(Get-NetIPAddress -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength,PrefixOrigin,AddressState)}
        if (-not $ready) { throw 'The fixed address did not become usable.' }
        $probe = [System.Net.NetworkInformation.Ping]::new()
        try { $reply = $probe.Send($managementAddress,1500) } finally { $probe.Dispose() }
        if ([string]$reply.Status -ne 'Success') { throw 'Management reachability was lost; restoring DHCP.' }
        $result.outcome = 'pin-complete'
    } else {
        if (-not ($addresses | Where-Object { $_.IPAddress -eq $pinnedAddress -and [string]$_.PrefixOrigin -eq 'Manual' }) -or
            [string]$ipInterface.Dhcp -ne 'Disabled') {
            throw 'The expected temporary fixed address is not present; no changes were made.'
        }
        Remove-NetIPAddress -InterfaceIndex $InterfaceIndex -IPAddress $pinnedAddress -Confirm:$false
        Set-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 -Dhcp Enabled -PolicyStore ActiveStore
        $result.outcome = 'dhcp-enabled'
        # This does not claim a lease was obtained. The router must have DHCP enabled first.
    }
    $result.after = @{dhcp=[string](Get-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4).Dhcp;
        addresses=@(Get-NetIPAddress -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength,PrefixOrigin,AddressState)}
} catch {
    $result.reason = $_.Exception.Message
    if ($changed) {
        try {
            Get-NetIPAddress -InterfaceIndex $InterfaceIndex -IPAddress $pinnedAddress -ErrorAction SilentlyContinue |
                Remove-NetIPAddress -Confirm:$false
            Set-NetIPInterface -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 -Dhcp Enabled -PolicyStore ActiveStore
            $result.rollback = 'dhcp-enabled'
        } catch { $result.rollback = 'failed' }
    }
} finally {
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultPath -Encoding UTF8
}
if ($result.outcome -eq 'stopped') { Write-Error $result.reason; exit 1 }
Write-Output ('Outcome: ' + $result.outcome)
Write-Output ('Report: ' + $resultPath)
