**Interfaz y Modelo de Clientes**

**Requerimientos del Módulo:**

1. Crear el modelo `Cliente` en `models.py` con los campos: `nombre_completo` (CharField), `email` (EmailField), `telefono` (CharField), `sexo` (CharField con choices M/F/Otro) y `documentacion` (FileField opcional, restringido a extensión `.pdf`).
2. Implementar un Validador Estricto en el modelo o formulario que rechace cualquier PDF que supere los 10 MB (10.485.760 bytes) de peso, para proteger el almacenamiento del servidor. Debe lanzar un error claro en el formulario si el archivo excede este tamaño.
3. Crear el formulario `ClienteForm` en `forms.py` que permita la carga de estos datos, validando tanto la extensión `.pdf` como el peso máximo de 10 MB del archivo en `request.FILES`.
4. Desarrollar las vistas en `views.py` para listar, crear, editar y eliminar clientes.
5. Diseñar la plantilla `clientes.html` de forma idéntica a la estética flat y monocromática del sistema. Debe mostrar la tabla de clientes, con columnas para Nombre Completo, Email, Teléfono, Sexo, Documentación (con un icono minimalista de PDF y texto "Subido" para descargar/ver, o un botón "Subir PDF" si no tiene) y las acciones habituales para editar/eliminar.
6. Configurar en `settings.py` la gestión de `MEDIA_URL` y `MEDIA_ROOT` para almacenar estos PDFs de forma local por el momento.

**Formato de Respuesta**
Comienza directamente escribiendo el código necesario (modelos, forms, vistas, urls y templates) para este módulo. Sé directo, técnico y no incluyas preámbulos. Asume responsabilidad absoluta sobre la eficiencia y seguridad del código entregado.

