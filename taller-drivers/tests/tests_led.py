#!/usr/bin/env python3
"""
SSOO - Ejercicio LED (/dev/led) - tests

Uso dentro de la VM, con el modulo cargado:
    sudo python3 tests/tests_led.py -v

"make test-led" compila, carga el modulo, corre los tests y lo descarga
al terminar, incluso si fallan. Requiere root para acceder a /dev/led.
No escribir en /dev/led desde otro proceso durante los tests.
"""
import errno
import os
import stat
import struct
import unittest

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


def _escribir(datos):
    dev = os.open(DEVICE, os.O_WRONLY)
    try:
        return os.write(dev, datos)
    finally:
        os.close(dev)


def _leer():
    dev = os.open(DEVICE, os.O_RDONLY)
    try:
        return os.read(dev, FORMATO.size)
    finally:
        os.close(dev)


class LedTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(DEVICE):
            raise AssertionError(
                f"no existe {DEVICE}: carga el modulo con 'make load-led'"
            )
        if not stat.S_ISCHR(os.stat(DEVICE).st_mode):
            raise AssertionError(f"{DEVICE} no es un dispositivo de caracteres")

    def setUp(self):
        # Cada test establece su propio estado, sin depender del orden.
        self.inicial = FORMATO.pack(1, 17, 83, 201, 0.5)
        self.assertEqual(_escribir(self.inicial), FORMATO.size)

    def _verificar_estado(self, status, color, brillo):
        enviado = FORMATO.pack(status, *color, brillo)
        self.assertEqual(_escribir(enviado), FORMATO.size)
        recibido = _leer()
        self.assertEqual(len(recibido), FORMATO.size)
        actual_status, r, g, b, actual_brillo = FORMATO.unpack(recibido)
        self.assertEqual(actual_status, status)
        self.assertEqual((r, g, b), color)
        # El float recibido tiene precision de 32 bits, no la de Python.
        self.assertAlmostEqual(actual_brillo, brillo, places=7)
        self.assertEqual(recibido, enviado, "el estado binario debe conservarse")

    def test_colores_rgb(self):
        for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255),
                      (255, 255, 255), (0, 0, 0), (12, 123, 234)):
            with self.subTest(color=color):
                self._verificar_estado(1, color, 1.0)

    def test_brillo_no_modifica_rgb(self):
        for brillo in (0.0, 0.3, 0.5, 1.0):
            with self.subTest(brillo=brillo):
                self._verificar_estado(1, (255, 80, 7), brillo)

    def test_apagar_y_prender_conserva_valores_enviados(self):
        for status in (0, 1, 0):
            with self.subTest(status=status):
                self._verificar_estado(status, (37, 149, 251), 0.3)

    def test_lectura_completa_y_fin_de_archivo(self):
        dev = os.open(DEVICE, os.O_RDONLY)
        try:
            self.assertEqual(os.read(dev, 32), self.inicial)
            self.assertEqual(os.read(dev, 32), b"")
        finally:
            os.close(dev)
        self.assertEqual(_leer(), self.inicial)

    def test_lecturas_parciales(self):
        dev = os.open(DEVICE, os.O_RDONLY)
        try:
            self.assertEqual(os.read(dev, 0), b"")
            partes = [os.read(dev, 1) for _ in range(FORMATO.size)]
            self.assertEqual(b"".join(partes), self.inicial)
            self.assertEqual(os.read(dev, 1), b"")
        finally:
            os.close(dev)

    def _verificar_rechazo(self, datos):
        with self.assertRaises(OSError) as ctx:
            _escribir(datos)
        self.assertEqual(ctx.exception.errno, errno.EINVAL)
        self.assertEqual(_leer(), self.inicial, "un error no debe cambiar el LED")

    def test_tamanos_invalidos(self):
        for datos in (b"1", self.inicial[:-1], self.inicial + b"x"):
            with self.subTest(tamano=len(datos)):
                self._verificar_rechazo(datos)

    def test_estado_invalido(self):
        for status in (2, 255):
            with self.subTest(status=status):
                self._verificar_rechazo(FORMATO.pack(status, 1, 2, 3, 1.0))

    def test_brillo_invalido(self):
        for brillo in (-0.1, 1.1, float("inf"), float("-inf"), float("nan")):
            with self.subTest(brillo=brillo):
                self._verificar_rechazo(FORMATO.pack(0, 1, 2, 3, brillo))

    def test_escritura_vacia_no_modifica_estado(self):
        self.assertEqual(_escribir(b""), 0)
        self.assertEqual(_leer(), self.inicial)


if __name__ == "__main__":
    unittest.main()
