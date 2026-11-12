**Contexto del Negocio**
Mi negocio ayuda a dueños de empresas a optimizar su flujo de caja, implementar el sistema "Profit First" (separación estricta de cuentas) y proteger su capital de la erosión monetaria mediante inversiones en el mercado de capitales (Balanz). La aplicación que estamos construyendo busca automatizar la ingesta de datos (archivos Excel/CSV), calcular puntos de equilibrio, distribuir flujos y proyectar interés compuesto.

**Infraestructura Técnica**

* **Backend:** Django, procesando datos matemáticos y financieros con `pandas`.
* **Base de Datos:** PostgreSQL 15.
* **Despliegue:** Monolito en Docker (Gunicorn + PostgreSQL + Nginx) alojado en una instancia AWS EC2 `t4g.small` (ARM, 2GB de RAM, 20GB SSD). Todo debe ser extremadamente ligero para no agotar la memoria.

**Reglas de Frontend Innegociables (AI_FRONTEND_GUIDELINES)**

1. **Estética Estoica:** Diseño minimalista y contable. Fondo predominante en blanco suavizado (ej. `#F8F9FA` o `#F5F5F5`). Todos los demás elementos en escala de grises y negros puros. Cero colores saturados, cero ruido cromático, cero animaciones superfluas.
2. **Rendimiento Máximo:** HTML/CSS puro y Vanilla JS (o HTMX). Prohibido el uso de frameworks frontend pesados (como React o Vue) y dependencias innecesarias.
3. **Ingesta Eficiente:** Los archivos subidos por los usuarios deben procesarse en memoria y desecharse. Prohibido guardarlos en el disco (volumen EBS).

**Instrucción de la Sesión**
En este chat nos enfocaremos de manera exclusiva y aislada en el desarrollo del siguiente módulo:
**Interfaz de Transacciones (Ingresos y Gastos)**

**Requerimientos del Módulo:**

1. Crear el modelo `Transaction` en `models.py` con los campos: Fecha, Tipo (Ingreso/Egreso), Monto, Concepto, y Cliente (Foreign Key a un modelo base de Cliente o User).
2. Crear un formulario basado en modelo (`ModelForm`) en `forms.py` para la carga individual.
3. Desarrollar la vista en `views.py` que permita listar las transacciones del usuario y procesar peticiones POST para crear, modificar o eliminar registros. Debe incluir lógica para procesar la subida masiva vía CSV/Excel en memoria (usando `pandas`).
4. Diseñar la plantilla `transactions.html`. La interfaz debe ser una tabla editable tipo hoja de cálculo con:
* Botón "+" para agregar una nueva fila de ingreso manual.
* Opciones en cada fila para modificar o eliminar.
* Un botón general de "Guardar Cambios" para confirmar las ediciones manuales.
* Un formulario de carga de archivos para la ingesta masiva (Excel/CSV).
* Todo esto debe funcionar mediante JavaScript puro (Vanilla JS) interceptando los formularios o usando la API Fetch para mantener la página sin recargas innecesarias, respetando estrictamente la paleta monocromática.



**Formato de Respuesta**
Comienza directamente escribiendo el código necesario (modelos, vistas, urls, forms y templates) para este módulo. Sé directo, técnico y no incluyas preámbulos ni conclusiones genéricas. Asume responsabilidad absoluta sobre la eficiencia del código entregado.
