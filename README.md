# Medical Device Kiosk

Application Django de borne medicale pour le pre-triage d'un patient, avec saisie manuelle et couche capteur optionnelle.

## Capteurs materiels

### VL53L1X avec Arduino

- VCC ou VIN vers `3.3V` ou `5V` selon le module
- GND vers `GND`
- SDA vers `A4`
- SCL vers `A5`

### Arduino vers Raspberry Pi

- Connecter l'Arduino au Raspberry Pi par cable USB
- Le port serie detecte est souvent `/dev/ttyACM0` ou `/dev/ttyUSB0`
- Baudrate attendu cote Django : `115200`

### MAX30102 avec Raspberry Pi

- VCC vers `3.3V` Raspberry Pi
- GND vers `GND`
- SDA vers `GPIO2` / pin 3
- SCL vers `GPIO3` / pin 5
- `INT` non obligatoire

### Activation I2C

```bash
sudo raspi-config
```

Puis :

- `Interface Options`
- `I2C`
- `Enable`

### Verification MAX30102

```bash
i2cdetect -y 1
```

Adresse attendue : `0x57`

## Installation

```bash
pip install -r requirements.txt
```

## Lancement Django

```bash
python manage.py runserver 0.0.0.0:8000
```
