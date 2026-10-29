#!/usr/bin/env python3
"""
SSOO - Ejercicio clave_valor (/dev/clave_valor) - tests

Uso (desde la raiz del taller, adentro de la VM, con el modulo ya cargado):
    sudo python3 tests/tests_clave_valor.py -v

Normalmente no hace falta invocarlo a mano: "make test-clave_valor" carga el
modulo, corre estos tests y lo descarga al terminar (pase lo que pase).

Requiere root: el nodo /dev/clave_valor, igual que /dev/nulo, solo es
legible/escribible por el dueño (root) en esta VM.
"""
import errno
import multiprocessing
import os
import unittest

DEVICE = "/dev/clave_valor"
CANTIDAD_CLAVES = 16

# La clave de LECTURA de este mismo proceso (el que corre los tests): se
# deriva del PID con la misma formula fija que usa el modulo. Se mantiene
# igual durante toda la corrida porque es un unico proceso Python.
MI_CLAVE = os.getpid() % CANTIDAD_CLAVES
OTRA_CLAVE = (MI_CLAVE + 1) % CANTIDAD_CLAVES

PROCESOS = 8
INCREMENTOS_POR_PROCESO = 200


def _leer_mi_clave(tam=32):
    dev = os.open(DEVICE, os.O_RDONLY)
    try:
        return int(os.read(dev, tam).decode().strip())
    finally:
        os.close(dev)


def _escribir_clave(clave, veces=1):
    dev = os.open(DEVICE, os.O_WRONLY)
    try:
        for _ in range(veces):
            os.write(dev, str(clave).encode())
    finally:
        os.close(dev)


def _escribir_muchas(clave, cantidad, barrera):
    # Se ejecuta en un proceso aparte (multiprocessing.Process). Cada
    # proceso tiene su propio PID (y por lo tanto su propia clave de
    # LECTURA), pero el write recibe la clave a incrementar de forma
    # explicita, asi que todos pueden apuntarle igual a la misma "clave"
    # sin importar cual sea la suya propia.
    dev = os.open(DEVICE, os.O_WRONLY)
    try:
        barrera.wait()  # arrancan todos lo mas juntos posible
        for _ in range(cantidad):
            os.write(dev, str(clave).encode())
    finally:
        os.close(dev)


class ClaveValorTestCase(unittest.TestCase):
    # La tabla es un estado global que persiste mientras el modulo siga
    # cargado, y este proceso siempre lee la misma clave (MI_CLAVE): una
    # vez que algun test la incrementa, ya no hay forma de volver a probar
    # "arranca en cero". unittest corre los tests en orden alfabetico por
    # nombre, asi que se numeran para dejar ese chequeo primero.

    def test_01_dispositivo_existe(self):
        self.assertTrue(
            os.path.exists(DEVICE),
            f"no existe {DEVICE}: ¿cargaste el modulo con 'make load-clave_valor'?",
        )

    def test_02_escribir_clave_fuera_de_rango_falla(self):
        dev = os.open(DEVICE, os.O_WRONLY)
        try:
            with self.assertRaises(OSError) as cm:
                os.write(dev, str(CANTIDAD_CLAVES).encode())
            self.assertEqual(cm.exception.errno, errno.EINVAL)

            with self.assertRaises(OSError) as cm:
                os.write(dev, b"-1")
            self.assertEqual(cm.exception.errno, errno.EINVAL)
        finally:
            os.close(dev)

    def test_03_escribir_no_entero_falla(self):
        dev = os.open(DEVICE, os.O_WRONLY)
        try:
            with self.assertRaises(OSError) as cm:
                os.write(dev, b"no-soy-un-numero")
            self.assertEqual(cm.exception.errno, errno.EINVAL)
        finally:
            os.close(dev)

    def test_04_mi_clave_arranca_en_cero(self):
        self.assertEqual(_leer_mi_clave(), 0)

    def test_05_escribir_incrementa_mi_clave(self):
        _escribir_clave(MI_CLAVE, veces=3)
        self.assertEqual(_leer_mi_clave(), 3)

    def test_06_escribir_otra_clave_no_afecta_la_mia(self):
        _escribir_clave(OTRA_CLAVE, veces=5)
        self.assertEqual(_leer_mi_clave(), 3)

    def test_07_incrementos_concurrentes_no_se_pierden(self):
        # Varios procesos incrementando a la vez la MISMA clave (la mia):
        # sin sincronizar el acceso a la tabla, un write puede pisar el
        # incremento de otro (leer-sumar-1-escribir no es atomico).
        base = _leer_mi_clave()

        barrera = multiprocessing.Barrier(PROCESOS)
        procesos = [
            multiprocessing.Process(
                target=_escribir_muchas, args=(MI_CLAVE, INCREMENTOS_POR_PROCESO, barrera)
            )
            for _ in range(PROCESOS)
        ]
        for p in procesos:
            p.start()
        for p in procesos:
            p.join()

        esperado = base + PROCESOS * INCREMENTOS_POR_PROCESO
        self.assertEqual(
            _leer_mi_clave(),
            esperado,
            "se perdieron incrementos: falta sincronizar el acceso a la tabla",
        )


if __name__ == "__main__":
    unittest.main()
