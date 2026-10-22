#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/cdev.h>
#include <linux/fs.h>
#include <linux/device.h>
#include <linux/uaccess.h>
#include <asm/io.h>

#include <linux/mutex.h>

// Usamos el registro de datos del puerto paralelo.
#define LED_PORT 0x378
#define LED_BIT_ON 0x01
#define LED_BIT_OFF 0x00

#define DEVICE_NAME "led"

// Formato binario compartido con Python ("<BBBBf"), 8 bytes:
// status (0/1), rojo, verde, azul.
// En C de usuario: bool status; uint8_t r, g, b; float brillo;
struct led_estado {
  u8 status;
  struct {
    u8 r, g, b;
  } color;
  __le32 brillo;
};

// Estado global del modulo, compartido por todos los procesos que abran
// /dev/led. El campo status de aca no es la fuente de verdad: el
// encendido/apagado real vive en el bit LED_BIT_ON del puerto.
static struct led_estado estado = {
  .color = { .r = 0, .g = 255, .b = 0 },
  .brillo = cpu_to_le32(0x3f800000), // 1.0f
};

static struct cdev led_device;
static dev_t led_dev;
static struct class *led_class;

static struct mutex mstate;

static ssize_t led_read(struct file *filp, char __user *data, size_t size,
                        loff_t *offset) {
  /* Completar:
   *  - Si ya se leyeron los 8 bytes (*offset >= sizeof(struct led_estado))
   *    o si size es 0, devolver 0 (fin de archivo).
   *  - Armar una copia del estado actual, con status tomado del bit
   *    LED_BIT_ON de LED_PORT (inb).
   *  - Copiar al usuario a partir de *offset, como mucho size bytes, 
        actualizar *offset y devolver cuantos se copiaron.
   */

  if(size == 0 || *offset >= sizeof(struct led_estado))
    return 0;
  
  if(size > sizeof(struct led_estado))
    size = sizeof(struct led_estado);

  struct led_estado state_copy = estado;

  mutex_lock(&mstate);
  state_copy.status = inb(LED_PORT);
  mutex_unlock(&mstate);

  int no_copiados = copy_to_user(data, (void *) &state_copy + *offset, size);
  int copiados = size - no_copiados;
  *offset += copiados;

  return copiados;
}

// Solo para el log: convierte un brillo ya validado a milesimas redondeadas.
static u32 brillo_milesimas(u32 bits) {
  u32 exponente = (bits >> 23) & 0xff;
  u32 desplazamiento;
  u64 escalado;

  // Estos valores son menores a media milesima (incluye ambos ceros).
  if (exponente < 116)
    return 0;

  desplazamiento = 150 - exponente;
  escalado = (u64) ((bits & 0x7fffff) | 0x800000) * 1000;
  return (escalado + (1ULL << (desplazamiento - 1))) >> desplazamiento;
}

    static ssize_t led_write(struct file *filp, const char __user *data, size_t size,
                          loff_t *offset) {
    /* Completar:
    *  - Una escritura vacia devuelve 0; cualquier otro tamaño distinto de
    *    sizeof(struct led_estado) es -EINVAL.
    *  - Copiar la estructura desde el usuario.
    *  - Validar status (0 o 1) y brillo (entre 0.0 y 1.0, sin negativos,
    *    infinitos ni NaN) sin usar floats. Pista: para floats positivos,
    *    comparar los bits como enteros da el mismo orden que comparar los
    *    numeros. Ojo con -0.0 (0x80000000), que tambien es valido.
    *  - Guardar el nuevo estado y escribir el bit de encendido en LED_PORT
    *    (outb).
    *  - Registrar la escritura con printk, con el formato del enunciado
    *    (usar brillo_milesimas para el brillo).
    */
    if(size == 0)
      return 0;
    else if(size != sizeof(struct  led_estado))
      return -EINVAL;

    struct led_estado new_state;
    if(copy_from_user(&new_state, data, size) != 0)
      return -EINVAL;

    if(new_state.status != 0 && new_state.status != 1)
      return -EINVAL;
    
    uint32_t brillo = le32_to_cpu(new_state.brillo);
    if(brillo > 0x3F800000 && brillo != 0x80000000)
      return -EINVAL;

    
    mutex_lock(&mstate);

    estado = new_state;
    outb(estado.status, LED_PORT);
    printk("led: LED %s, RGB(%d, %d, %d), brillo=0.%d", 
      estado.status ? "ON" : "OFF", 
      estado.color.r, 
      estado.color.g, 
      estado.color.b, 
      brillo_milesimas(le32_to_cpu(estado.brillo)));

    mutex_unlock(&mstate);    

    return size;
  }

static struct file_operations led_operaciones = {
  .owner = THIS_MODULE,
  // Completar
  .read = led_read,
  .write = led_write
};

static int __init led_init(void) {

  /* Completar: crear el character device y dejar el LED apagado. */
  cdev_init(&led_device, &led_operaciones);
  alloc_chrdev_region(&led_dev, 0, 1, DEVICE_NAME);
  cdev_add(&led_device, led_dev, 1);

  led_class = class_create(THIS_MODULE, DEVICE_NAME);
  device_create(led_class, NULL, led_dev, NULL, DEVICE_NAME);

  mutex_init(&mstate);

  mutex_lock(&mstate);
  outb(LED_BIT_OFF, LED_PORT);
  estado = (struct led_estado) {
    .status = LED_BIT_OFF,
    .color = {.r = 0, .g = 255, .b = 0},
    .brillo = cpu_to_le32(0x3F800000)
  };
  mutex_unlock(&mstate);    

  return 0;
}

static void __exit led_exit(void) {
  /* Completar: apagar el LED y destruir el character device. */

  mutex_lock(&mstate);
  outb(LED_BIT_OFF, LED_PORT);
  estado = (struct led_estado) {
    .status = LED_BIT_OFF,
    .color = {.r = 0, .g = 255, .b = 0},
    .brillo = cpu_to_le32(0x3F800000)
  };
  mutex_unlock(&mstate);  
  
  device_destroy(led_class, led_dev);
  class_destroy(led_class);

  cdev_del(&led_device);
  unregister_chrdev_region(led_dev, 1);

  mutex_destroy(&mstate);
}

module_init(led_init);
module_exit(led_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("La banda de SO");
MODULE_DESCRIPTION("LED controlado por el puerto paralelo con outb e inb");
