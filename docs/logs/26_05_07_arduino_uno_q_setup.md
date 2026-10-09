# Arduino Uno Q - TCC - 07/05/2026



Repo base usado: <https://github.com/Mjrovai/ARDUINO-UNO-Q>

Outras fontes:

- https://www.jeffgeerling.com/blog/2025/arduino-uno-q-weird-hybrid-sbc/
- https://techexplorations.com/blog/arduino/arduino-uno-q-person-detector-bridge-bricks-and-real-time-ai/
- https://myembeddedstuff.com/arduino-uno-q-boot-time
- https://community.element14.com/products/roadtest/b/blog/posts/arduino-uno-q---applab-initial-configuration-and-examples
- https://www.xda-developers.com/built-clipboard-server-arduino-uno-q-replaced-workflow/
- https://docs.edgeimpulse.com/hardware/boards/arduino-uno-q
- https://robocraze.com/blogs/post/arduino-uno-q-sbc-common-problems-troubleshooting-guide


## Meios de Conexão e Programação:

1 - Arduino App Lab:

- Vantagens:

  - Sem setup.

  - Componentes prontos para teste rápido.

  - Bridge (conexão entre chips) feita automaticamente.

  - Dashboard em tempo real.

- Desvantagens:

  - Extremamente pesado (usa containers docker para cada brick usado,
    consumindo RAM e CPU).

  - Adiciona uma camada de latência.

  - Alto consumo de armazenamento

  - Precisa de WiFi (bug)

  - Ainda está em beta.
  
  

2 - SSH + WiFi:

- Vantagens:
  - Mais performance.
  
  - Uso de IDE da sua escolha.
  
  - Maior controle de código, versionamento e recursos do
    sistema.
  
  - Pode utilizar o `arduino-app-cli`.
  
- Desvantagens::
- Precisa de WiFi para conexão.
  
- Precisa ter cuidado para não encher a memória da placa com
    artefatos de extensões do VSCode.

- Servidor Remoto das IDEs consumem muita memória da placa.



3 - ADB sobre USB-C:

- Vantagens:

  - Existe documentação oficial da Arduino para fazer a conexão (
    <https://docs.arduino.cc/tutorials/uno-q/adb/> )

  - Não precisa de nenhuma conexão sem fio (menos consumo).

  - Não precisa estar conectado em produção.

- Desvantagens:

  - Não pode usar os bricks prontos do App Lab

  - O desenvolvimento é feito todo localmente e só depois deve 
  
  - Precisa pensar em um meio de extrair os dados da aplicação e do
    estado da placa (provavelmente será feito armazenando e pegando os
    resultados depois de rodar).
    
  - Desenvolvimento de código deve ser feito separado e fazer o deploy depois.



**Abordagem Escolhida:** Opção 3 (ADB sobre USB-C)



## Passo a Passo do Setup:

Conectar e atualizar:

```bash
# Conectar no Arduino por ADB - meu PC:

sudo dnf install android-tools
adb version # Verificar
adb devices # Ver se Arduino conectou
adb shell # Conectar de fato

# já conectado:

sudo apt update
sudo apt upgrade
```

Na minha abordagem, eu escolhi priorizar performance e vi que muita memória está sendo ocupada por aplicativos que eu nunca vou usar (chromium, etc.).

Caso eu desinstale algum app que vou usar depois, é só reinstalar. Nesse caso, o próximo passo é realizar um `purge` nos arquivos do Arduino Uno Q:

```bash
# Obter arquivo txt com programas instalados:

dpkg-query -W -f='${Installed-Size}\t${Package}\t${binary:Summary}\n' | sort -nr | awk -F'\t' '{printf "%8.1f MB  %-40s  %s\n", $1/1024, $2, $3}' > ./installed.txt
```

Para transferir o arquivo:

```bash
# Em outro terminal (No PC):

adb pull /home/arduino/installed.txt . 
```

Usando uma LLM para filtrar os programas, eu escolho quais eu vou apagar os programas com o comando:

```bash
# De volta no Arduino Uno Q:

# Pacotes "óbvios" descartáveis
sudo apt purge \
  chromium chromium-common \
  pocketsphinx-en-us libpocketsphinx3 libsphinxbase3t64 \
  libflite1 \
  fonts-noto-color-emoji fonts-droid-fallback fonts-urw-base35 \
  evolution-data-server-common \
  poppler-data libpoppler147 libpoppler-glib8t64 \
  libgs10 libgs10-common libgs-common ghostscript \
  synaptic \
  vim-runtime vim-common vim-tiny \
  desktop-base adwaita-icon-theme tango-icon-theme \
  libmagickcore-7.q16-10 libmagickwand-7.q16-10 imagemagick-7-common \
  timgm6mb-soundfont libwildmidi2 libfluidsynth3 \
  libdjvulibre-text libdjvulibre21

sudo apt autoremove --purge

```

Resultado:

```bash
arduino@uno2GB:~$ df -h
Filesystem       Size  Used Avail Use% Mounted on
udev             842M     0  842M   0% /dev
tmpfs            175M  1.5M  173M   1% /run
/dev/mmcblk0p68  9.8G  5.6G  3.7G  60% /
tmpfs            871M     0  871M   0% /dev/shm
efivarfs         128K  2.2K  126K   2% /sys/firmware/efi/efivars
tmpfs            5.0M  8.0K  5.0M   1% /run/lock
tmpfs            871M  4.0K  871M   1% /tmp
tmpfs            1.0M     0  1.0M   0% /run/credentials/systemd-journald.service
/dev/mmcblk0p69  3.6G  565M  2.9G  17% /home/arduino
/dev/mmcblk0p67  488M  119M  369M  25% /boot/efi
tmpfs            1.0M     0  1.0M   0% /run/credentials/getty@tty1.service
tmpfs            1.0M     0  1.0M   0% /run/credentials/serial-getty@ttyMSM0.service
```



# Configurando WiFi e Server SSH

Para conectar o wifi e criar a conta do arduino, eu usei o Arduino App Lab por uma questão de economizar tempo. Eu testei com um simples comando de ping. Também utilizei os comandos:

```bash
nmcli device status
hostname -I
```

O hostname vai entregar também o IP que o arduino está usando na rede, ele será usado para conectar o SSH, no meu caso `192.168.0.105`

Para ativar o servidor SSH:

```bash
arduino-app-cli system network-mode enable 
```

Criar a chave e conectar:

```bash
ssh-keygen -t ed25519
ssh-copy-id arduino@<UNO_Q_IP_ADDRESS>

ssh arduino@<UNO_Q_IP_ADDRESS>
```



# Arduino App CLI Terminal

Ao invés de usar App Lab, também é possível usar:

```bash
arduino-app-cli app new "<name>"

arduino-app-cli app list

arduino-app-cli app start name

arduino-app-cli app logs . --follow

arduino-app-cli app stop name

arduino-app-cli system cleanup

arduino-app-cli system update
```







