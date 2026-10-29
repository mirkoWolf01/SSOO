#!/usr/bin/env python3
"""
SSOO - Ejercicio Nulo (/dev/nulo) - tests

Uso (desde la raiz del taller, adentro de la VM, con el modulo ya cargado):
    sudo python3 tests/tests_nulo.py -v

Normalmente no hace falta invocarlo a mano: "make test-nulo" carga el modulo,
corre estos tests y lo descarga al terminar (pase lo que pase).

Requiere root: el nodo /dev/nulo, igual que /dev/null, solo es
legible/escribible por el dueño (root) en esta VM.

Como /dev/nulo debe comportarse "exactamente" como /dev/null, buena parte
de los tests comparan directamente contra el dispositivo real en vez de
fijar valores a mano.
"""
import os
import unittest

DEVICE = "/dev/nulo"
REFERENCE = "/dev/null"


class NuloTestCase(unittest.TestCase):
    def test_dispositivo_existe(self):
        self.assertTrue(
            os.path.exists(DEVICE),
            f"no existe {DEVICE}: ¿cargaste el modulo con 'make load-nulo'?",
        )

    # Se usan os.open/os.read/os.write "a mano" (en vez de fdopen +
    # objetos file de Python) porque un character device no es seekable,
    # y el io con buffer de Python necesita poder buscar para abrir en
    # modo lectoescritura.

    def test_lectura_devuelve_vacio(self):
        dev = os.open(DEVICE, os.O_RDONLY)
        try:
            self.assertEqual(os.read(dev, 10), b"")
        finally:
            os.close(dev)

    def test_lectura_se_comporta_como_dev_null(self):
        nulo = os.open(DEVICE, os.O_RDONLY)
        null = os.open(REFERENCE, os.O_RDONLY)
        try:
            for tam in (0, 1, 10, 4096):
                self.assertEqual(os.read(nulo, tam), os.read(null, tam))
        finally:
            os.close(nulo)
            os.close(null)

    def test_escritura_acepta_todo_el_buffer(self):
        dev = os.open(DEVICE, os.O_WRONLY)
        try:
            self.assertEqual(os.write(dev, b"Hola!"), 5)
            self.assertEqual(os.write(dev, b"Hola! Sistema Operativo"), 23)
            self.assertEqual(os.write(dev, b"x" * 65536), 65536)
        finally:
            os.close(dev)

    def test_escritura_no_altera_lecturas_posteriores(self):
        dev = os.open(DEVICE, os.O_RDWR)
        try:
            os.write(dev, b"esto se descarta")
            self.assertEqual(os.read(dev, 10), b"")
        finally:
            os.close(dev)


if __name__ == "__main__":
    unittest.main()
