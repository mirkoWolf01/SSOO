#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/cdev.h>
#include <linux/fs.h>
#include <linux/device.h>
#include <linux/uaccess.h>
#include <linux/sched.h>

#define BUFFER_SIZE 32
#define CANTIDAD_CLAVES 16

#define DEVICE_NAME "clave_valor"

// Estado global del modulo: una tabla de CANTIDAD_CLAVES casilleros
// compartida por todos los procesos que abran /dev/clave_valor (no una
// tabla por cada apertura).
static long tabla[CANTIDAD_CLAVES];

static struct mutex mtable;

// El read no recibe ninguna clave: cada proceso solo puede leer SU PROPIO
// casillero. Pista: calcular la clave usando el PID del proceso que llama.
static ssize_t clave_valor_read(struct file *filp, char __user *data, size_t size, loff_t *offset) {
  /* Completar */

  pid_t pid = task_tgid_nr(current);
  int slot = pid % CANTIDAD_CLAVES;

  long val; 
  mutex_lock(&mtable);
  val = tabla[slot];
  mutex_unlock(&mtable);

  char buff[BUFFER_SIZE];
  int len = snprintf(buff, BUFFER_SIZE, "%ld\n", val);
  copy_to_user(data, &buff, len);

  return len;
}

// El write si recibe una clave (como texto, en el buffer): la clave de la
// tabla que hay que incrementar en 1. No hace falta mandar nada mas: el
// incremento siempre es de a uno.
static ssize_t clave_valor_write(struct file *filp, const char __user *data, size_t size, loff_t *offset) {
  /* Completar */
  char clave_str[BUFFER_SIZE]; 
  if(copy_from_user(&clave_str, data, size) != 0)
    return -EINVAL;

  int clave; 
  if(kstrtoint(clave_str, 0, &clave) != 0)
    return -EINVAL;
  
  if(clave < 0 || clave > CANTIDAD_CLAVES - 1)
    return -EINVAL;

  mutex_lock(&mtable);
  tabla[clave]++;
  mutex_unlock(&mtable);
  
  return size;
}

static struct file_operations clave_valor_operaciones = {
  .owner = THIS_MODULE,
  // Completar
  .read  = clave_valor_read,
  .write = clave_valor_write,
};

static struct cdev clave_valor_device;
static dev_t major;
static struct class *clave_valor_class;

static int __init clave_valor_init(void) {

  /* Completar */
  cdev_init(&clave_valor_device, &clave_valor_operaciones);
  alloc_chrdev_region(&major, 0, 1, DEVICE_NAME);
  cdev_add(&clave_valor_device, major, 1);

  clave_valor_class = class_create(THIS_MODULE, DEVICE_NAME);
  device_create(clave_valor_class, NULL, major, NULL, DEVICE_NAME);

  mutex_init(&mtable);

  mutex_lock(&mtable);
  for(int i = 0; i < CANTIDAD_CLAVES; i++)
    tabla[i] = 0;
  mutex_unlock(&mtable);
  return 0;
}

static void __exit clave_valor_exit(void) {
  /* Completar */
  device_destroy(clave_valor_class, major);
  class_destroy(clave_valor_class);

  cdev_del(&clave_valor_device);
  unregister_chrdev_region(major, 1);

  mutex_destroy(&mtable);
}

module_init(clave_valor_init);
module_exit(clave_valor_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("La banda de SO");
MODULE_DESCRIPTION("Una base de datos clave-valor muy simplificada");
