# Computer Vision Sprint

Data de início: 18/06/2026

 **Setup provisório para teste**:

![[obj_det_setup.png]]

## Board + Camera + Baseline

Conectei na placa utilizando o Arduino App Lab para obter o terminal de acesso ao SO da placa de forma mais fácil (não necessita saber o IP previamente).

Com a camera USB conectada no dock alimentado, rodei o seguinte comando e verifiquei que ela está funcionando:

```bash
lsusb
```

Para ver as resoluções disponíveis da câmera:

```bash
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Formato escolhido: 1080 x 920 (16 : 9) - 30 FPS

Criar symlink para não verificar qual entrada de vídeo está toda vez:

```bash
# List symlinks
ls -l /dev/v4l/by-id/ 

# Add to Environment
echo 'export VIDEO_DEVICE=/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0' >> ~/.bashrc

# Apply and confirm
source ~/.bashrc
echo "$VIDEO_DEVICE"
```
 
## Arduino App CLI:

```bash
# Create App:
arduino-app-cli app new "name"

# Start App:
arduino-app-cli app start "path/name"
arduino-app-cli app start "user:name" # Created by me
arduino-app-cli app start "examples:name"

# Stop App:
arduino-app-cli app stop "path/name"

# Read Logs:
arduino-app-cli app logs "path/name" --all

# List Apps:
arduino-app-cli app list

# -------------------------------------------------

# Update system:
arduino-app-cli system update

# Clean up:
arduino-app-cli system cleanup

# set board-name:
arduino-app-cli system set-name "my-board"

# Disable/enable network:
arduino-app-cli system network enable/disable

# -------------------------------------------------

# Bricks can only be listed or detailed through CLI
arduino-app-cli brick list

arduino-app-cli brick details arduino:<brick>

```

## How App Lab gives camera ownership?

Test code:

```py
import time
import cv2

from arduino.app_utils import App  # pyright: ignore[reportMissingImports]

print("Starting camera testing - Will the arduino App be able to get the camera ownership from the OS?")

cap = cv2.VideoCapture(0)

print("opened:", cap.isOpened())

ok, frame = cap.read()
print("read:", ok, None if frame is None else frame.shape)
cap.release()

App.run()
```

Results: It ran successfully, the Docker container created by the App uses the camera directly from the OS.

## Tuning the Camera

Para saber os parâmetros de configuração da câmera:

```bash
v4l2-ctl -d /dev/video2 --list-ctrls
```

Rodar uma vez para desabilitar foco, deixar o controle de exposure manual, desabilitar wb, fixar framerate e escolher a frequência (1 - Americas):

```bash
DEV="$VIDEO_DEVICE"

v4l2-ctl -d "$DEV" -c focus_automatic_continuous=0   # autofocus OFF
v4l2-ctl -d "$DEV" -c auto_exposure=1                # exposure → manual
v4l2-ctl -d "$DEV" -c white_balance_automatic=0      # auto WB OFF
v4l2-ctl -d "$DEV" -c exposure_dynamic_framerate=0   # fixed framerate
v4l2-ctl -d "$DEV" -c power_line_frequency=1         # 1=50Hz, 2=60Hz
``` 

Deixar no padrão:

- zoom_absolute=100
- pan_absolute=0
- tilt_absolute=0
- brightness=128
- contrast=128
- sharpness=128
- saturation=128
- backlight_compensation=0

Ajustados manualmente por iteração (ainda vai ser modificado):

```bash
v4l2-ctl -d $VIDEO_DEVICE -c gain=
v4l2-ctl -d $VIDEO_DEVICE -c white_balance_temperature=
v4l2-ctl -d $VIDEO_DEVICE -c exposure_time_absolute=
v4l2-ctl -d $VIDEO_DEVICE -c focus_absolute=
```

- **focus_absolute**: 0 = focused far (infinity), and higher → focused closer
- **exposure_time_absolute**: How long the sensor collects light per frame, in units of 100 µs (so 156 = 15.6 ms). Longer = brighter but more blur; shorter = crisper through motion but darker.
- **gain**: It brightens _without_ lengthening exposure, but it amplifies **noise**.
- **white_balance_temperature**: Corrects the color cast of your light (2800 = warm/incandescent → 6500 = cool/daylight). It is more important to be consistent than exactly right.

## Create Frame Handler Brick

O App não tem um tutorial claro de como criar um brick (nem a documentação do site), mas após uma pesquisa, existe um guia online:

https://deepwiki.com/arduino/app-bricks-py/3-brick-development-guide

Eu segui esse guia e montei uma função simples de camera usando opencv para servir de interface de API. Infelizmente, para meu modelo de câmera, o opencv aparenta ter alguns bugs e não consegue definir os parâmetros da câmera pelo cap, fazendo você ter que configurar manualmente.

```py
class Camera:
    def __init__(self, device=None, width=1280, height=720):
        self._device = device or os.environ.get(
            "VIDEO_DEVICE", "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0"
        )
        self._width, self._height = width, height
        self._cap = None

    def open(self, warm_up_seconds=2):
        self._cap = cv2.VideoCapture(self._device)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        if not self._cap.isOpened():
            raise RuntimeError("[Camera] Failed to open camera")

        deadline = time.time() + warm_up_seconds
        while time.time() < deadline:
            ret, _ = self._cap.read()
            if ret:
                return

    def read(self):
        if self._cap is None:
            raise RuntimeError("[Camera] Camera is not opened")
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("[Camera] Failed to read frame")
        return frame

    def release(self):
        self._cap.release()
```

## Sub-projeto Obj. Detection: Dexter e Doc

Embora a câmera não pode ter os parâmetros tunados propriamente para esse problema, decidi capturar o dataset do Dexter e do Doc de qualquer forma para poder apresentar algo na demo de quinta.

### Capturar o Dataset:

Usando o Arduino Uno Q e minha câmera alvo para capturar o dataset, eu retirei diversas fotos com os bonecos do Dexter e do Doc Brown, além de diversas fotos apenas do plano de fundo.

Utilizei o script fornecido pelo Rovai, com a modificação do meu Brick, para capturar cada uma das imagens:

```py
label = "docBrown"  # Change for each class
output_dir = f"/home/arduino/dataset/{label}"
os.makedirs(output_dir, exist_ok=True)

cam = Camera()

cam.open()

count = 0

print(f"Capturing images for class '{label}'. Press Ctrl+C to stop.")

record = 'y'

while(record != 'N'):
	frame = cam.read()
	filename = f"{output_dir}/{label}_{count:03d}.jpg"
	cv2.imwrite(filename, frame)
	print(f"Saved: {filename}")
	count += 1
	record = input("Continue? N to stop")

cam.release()


print(f"Captured {count} images for '{label}'.")
```

### Manual Labeling:

Após isso, para todas as imagens, eu manualmente selecionei todos os bonecos usando a própria ferramenta do Edge Impulse.

![[Pasted image 20260623002515.png]]

![[Pasted image 20260623003105.png]]

**Por que Edge Impulse?** 

- Prototipagem rápida end-to-end
	- Coleta de Dados
	- Ferramentas de Labeling
	- Diversos modelos para teste
	- Fine Tuning do Modelo sem Hardware próprio
	- Testes do modelo (Test set + Real Time)
	- Deploy rápido
- Integração pronta com Arduino App Lab (Qualcomm comprou Arduino)

**Vai ser usado para o projeto final?** 

Talvez, ainda não tenho certeza da minha decisão final (PyTorch vs Edge Impulse), mas não me importa muito para agora, pois o objetivo do projeto em si não é estudar técnicas de treinamento de modelos de rede neural, mas sim a integração dos modelos em sistemas embarcados para minha aplicação.

### Criar modelos

O Edge Impulse permite (no plano free) que você tenha até 10 testes de modelos salvos (Impulses).

Eu testei os seguintes abaixo:

![[Pasted image 20260623142443.png]]

**Modelos de teste escolhidos:**

- MobileNetV2: modelo menor que o YOLO e possui resultados muito bons normalmente, mas infelizmente, no Edge Impulse, só aceita imagens 320 x 320 como entrada, aumentando consideravelmente a latência.

- Yolo-Pro: YOLO (You Only Look Once), arquitetura famosa e muito usada para tarefas de visão computacional. Essa versão é desenvolvida em cima do YOLO v8, com uma performance melhorada.

### Fast Deploy:

Testando com o App de Detecção de Objetos pronto, fornecido pelo Arduino App Lab como um app experimental:

![[demo_app_pronto_dexter_doc.mp4]]

### Personalized Deploy with Bridge Integration:

4 candidatos pelos testes:

- yolo-pro-128-x-128-attention
- yolo-pro-128-x-128
- yolo-pro-160-x-160-attention
- yolo-pro-160-x-160

Modelos nos testes na maioria das vezes não se comportam tão bem na realidade.

#### Teste 1: 128 x 128 Attention 

- Grandes dificuldades de encontrar o docBrown a partir de 60% da arena.
- Muitas oscilações nas bounding boxes do docBrown.
- Dificuldades de identificar docBrown com Dexter (Sem dados no Dataset).
- Poucos casos de confusão do docBrown para Dexter.
- Alguns casos de confusão do Dexter para o docBrown (depende da posição).

#### Teste 2: 128 x 128

- Herda grande parte dos problemas do de cima.
- Melhora um pouco a detecção do docBrown, mas pareceu piorar um pouco a do Dexter.

#### Teste 3: 160 x 160 Attention 

- Um pouco de melhora em relação aos outros, mas ainda ocorre confusão de forma relativamente próxima.

#### Teste 4: 160 x 160

- Detecção ótima do Dexter
- Detecção do Dr. Brown falhou em partes apenas na última linha.
- Dificuldade de identificar ambas as classes juntas.

#### Veredito:

Usarei para a demo o Yolo Pro 160 x 160 sem atenção, melhor resultado na inferência.

![[Demo_dex.mp4]]