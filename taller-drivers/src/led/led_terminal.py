#!/usr/bin/env python3
import argparse
import os
import shlex
import struct
import sys
import time

DEVICE = "/dev/led"
# Símbolo    Significado                                      Tamaño
# ---------  -----------------------------------------------  -------
# <          Orden little-endian, sin padding entre campos     —
# Primer B   Entero sin signo: estado 0 o 1                    1 byte
# Segundo B  Rojo, de 0 a 255                                 1 byte
# Tercer B   Verde, de 0 a 255                                1 byte
# Cuarto B   Azul, de 0 a 255                                 1 byte
# f          Brillo como float IEEE 754 de 32 bits             4 bytes
#
# Total: 8 bytes. B admite cualquier valor entre 0 y 255;
# que el estado sea solo 0 o 1 lo valida el driver.
FORMATO = struct.Struct("<BBBBf")


def validar_estado(status, r, g, b, brillo):
    if status not in (0, 1):
        raise ValueError("status debe ser 0 o 1")
    if any(not 0 <= canal <= 255 for canal in (r, g, b)):
        raise ValueError("los canales RGB deben estar entre 0 y 255")
    if not 0 <= brillo <= 1:
        raise ValueError("brillo debe estar entre 0 y 1")


def leer_estado(device):
    with open(device, "rb", buffering=0) as archivo:
        datos = archivo.read(FORMATO.size)
    if len(datos) != FORMATO.size:
        raise ValueError(f"se esperaban {FORMATO.size} bytes, llegaron {len(datos)}")
    estado = FORMATO.unpack(datos)
    validar_estado(*estado)
    return estado


def escribir_estado(device, status, color, brillo):
    validar_estado(status, *color, brillo)
    datos = FORMATO.pack(status, *color, brillo)
    # Una sola escritura: el driver recibe una estructura completa.
    fd = os.open(device, os.O_WRONLY)
    try:
        if os.write(fd, datos) != len(datos):
            raise OSError("escritura incompleta del estado del LED")
    finally:
        os.close(fd)


def dibujar(valores, device=DEVICE):
    encendido, r, g, b, brillo = valores
    print("\033[2J\033[H", end="", flush=True)
    estado = "ENCENDIDO" if encendido else "APAGADO"

    if encendido and brillo > 0 and any((r, g, b)):
        rojo, verde, azul = (round(canal * brillo) for canal in (r, g, b))
        color_led = f"\033[38;2;{rojo};{verde};{azul}m"
        color_borde = color_led
        color_estado = color_led
        relleno = "██████████████"
        rayos = [
            "        \\  |  /        ",
            "         \\ | /         ",
            "      ---- * ----      ",
        ]
    else:
        color_led = "\033[38;5;236m"
        color_borde = "\033[38;5;245m"
        color_estado = "\033[38;5;245m"
        relleno = "▓▓▓▓▓▓▓▓▓▓▓▓▓▓"
        rayos = [
            "                       ",
            "                       ",
            "                       ",
        ]

    reset = "\033[0m"
    print(color_borde + "\n".join(rayos) + reset)
    print(color_borde + "        .--------.        " + reset)
    print(color_borde + "      .'          '.      " + reset)
    print(color_borde + "     /" + color_led + relleno + color_borde + "\\     " + reset)
    print(color_borde + "    |" + color_led + "████  LED  ████" + color_borde + "|    " + reset)
    print(color_borde + "     \\" + color_led + relleno + color_borde + "/     " + reset)
    print(color_borde + "      '.          .'      " + reset)
    print(color_borde + "        '--------'        " + reset)
    print(color_borde + "           |  |           " + reset)
    print(color_borde + "           |  |           " + reset)
    print(color_borde + "        ___|__|___        " + reset)
    print()
    print(f"{device}: {color_estado}{estado}{reset}")
    print(f"RGB: ({r}, {g}, {b}) | Brillo: {brillo:.2f}")
    print()
    print("En otra terminal de la VM:")
    comando = f"sudo python3 {shlex.quote(sys.argv[0])} --device {shlex.quote(device)}"
    print(f"  {comando} --status 1 --color 255 80 0 --brillo 0.5")
    print(f"  {comando} --status 0")
    print()
    print("Ctrl-C para salir.")


def main():
    parser = argparse.ArgumentParser(
        description="Visualiza o escribe el estado binario de /dev/led"
    )
    parser.add_argument("--device", default=DEVICE)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--status", type=int, choices=(0, 1),
                        help="envia el estado y sale: 0 apagado, 1 prendido")
    parser.add_argument("--color", type=int, nargs=3, metavar=("R", "G", "B"),
                        help="canales RGB de 0 a 255; por defecto conserva el color")
    parser.add_argument("--brillo", type=float,
                        help="valor de 0 a 1; por defecto conserva el brillo")
    args = parser.parse_args()
    if not 0 < args.interval < float("inf"):
        parser.error("--interval debe ser un numero positivo y finito")
    if args.status is None and (args.color is not None or args.brillo is not None):
        parser.error("--color y --brillo requieren --status")
    if args.color is not None and any(not 0 <= canal <= 255 for canal in args.color):
        parser.error("los canales RGB deben estar entre 0 y 255")
    if args.brillo is not None and not 0 <= args.brillo <= 1:
        parser.error("--brillo debe estar entre 0 y 1")

    if not os.path.exists(args.device):
        print(
            f"No existe {args.device}. Carga el modulo con sudo insmod led.ko.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.status is not None:
            color, brillo = args.color, args.brillo
            if color is None or brillo is None:
                _, r, g, b, brillo_actual = leer_estado(args.device)
                if color is None:
                    color = (r, g, b)
                if brillo is None:
                    brillo = brillo_actual
            escribir_estado(args.device, args.status, color, brillo)
            return 0
        while True:
            dibujar(leer_estado(args.device), args.device)
            time.sleep(args.interval)
    except (OSError, ValueError) as error:
        print(f"No se pudo acceder a {args.device}: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\033[2J\033[H", end="", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
