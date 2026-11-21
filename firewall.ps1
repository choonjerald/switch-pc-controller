param(
    [string]$PcAddress,
    [string]$SwitchAddress,
    [switch]$WebSocket,
    [switch]$Remove
)
$ErrorActionPreference = 'Stop'
$group = 'SwitchPCController diagnostic'
if ($Remove) {
    Get-NetFirewallRule -Group $group -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    return
}
function Test-PrivateIPv4([string]$value) {
    $ip = $null
    if (![ipaddress]::TryParse($value, [ref]$ip)) { return $false }
    $b = $ip.GetAddressBytes()
    return ($b.Length -eq 4 -and $ip.ToString() -eq $value -and (
        $b[0] -eq 10 -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or
        ($b[0] -eq 192 -and $b[1] -eq 168)))
}
if (!(Test-PrivateIPv4 $PcAddress) -or !(Test-PrivateIPv4 $SwitchAddress) -or $PcAddress -eq $SwitchAddress) {
    throw 'Supply the distinct private IPv4 addresses of the PC and the Switch.'
}
$ports = @(@{Name='DNS'; Protocol='UDP'; Port=53}, @{Name='HTTP'; Protocol='TCP'; Port=80})
if ($WebSocket) { $ports += @{Name='WebSocket'; Protocol='TCP'; Port=8765} }
foreach ($rule in $ports) {
    $name = 'SwitchPCController-Diagnostic-' + $rule.Name
    Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -Name $name -DisplayName "$group $($rule.Name)" -Group $group -Direction Inbound -Action Allow -Profile Private -Protocol $rule.Protocol -LocalPort $rule.Port -LocalAddress $PcAddress -RemoteAddress $SwitchAddress | Out-Null
}
