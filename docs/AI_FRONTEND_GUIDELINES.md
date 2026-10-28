# AI Frontend & Architecture Guidelines (System Skills)

Este documento establece las **reglas innegociables** que cualquier agente de IA o desarrollador debe cumplir estrictamente al generar nuevas interfaces, plantillas, vistas o flujos de datos dentro de `accounting_data`.

---

## 1. Estética Visual (Minimalista, Estoica y Contable)

* **Paleta de Colores Estrictamente Acromática:**
  * **Fondo principal (`--bg-primary`):** Blanco suavizado (`#F8F9FA` o `#F5F5F5`). **Nunca usar blanco puro (`#FFFFFF`)** como fondo general.
  * **Superficies y contenedores secundarios (`--bg-surface`):** Escala de grises claros (`#EFEFEF` a `#F2F2F2`).
  * **Texto principal (`--text-primary`):** Gris carbón / casi negro (`#1A1A1A`).
  * **Texto secundario / metadatos (`--text-secondary`):** Gris medio-oscuro (`#4D4D4D` o `#666666`).
  * **Bordes y divisores (`--border-color`):** Gris neutro (`#E0E0E0` o `#CCCCCC`).
  * **Acciones primarias / Botones:** Fondo `#1A1A1A` con texto `#F8F9FA`, o borde sólido `1px solid #1A1A1A` sobre fondo `#F2F2F2`.
* **Prohibición de Ruido Cromático:** Queda terminantemente prohibido el uso de colores saturados, gradientes decorativos, sombras difusas excesivas o iconografía superflua. La jerarquía visual se construye exclusivamente mediante tipografía, espaciado, grosor de línea y contraste en escala de grises.
* **Tipografía y Tablas:** Priorizar fuentes monoespaciadas o sans-serif geométricas del sistema con `font-variant-numeric: tabular-nums` para garantizar la alineación vertical exacta de cifras contables.

---

## 2. Rendimiento y Arquitectura Frontend

* **Cero Frameworks Pesados:** Queda prohibido introducir SPAs o librerías pesadas (React, Vue, Angular, Tailwind vía CDN en tiempo de ejecución, Bootstrap completo).
* **Stack Permitido:** HTML5 semántico renderizado en servidor (Django Templates), CSS puro (Variables CSS nativas, Grid, Flexbox) y **Vanilla JS** (o **HTMX** ligero cuando se requiera interactividad parcial sin recarga completa).
* **Diseño Responsive Obligatorio:** Todas las interfaces deben ser completamente *responsive* y adaptarse con fluidez a cualquier resolución (escritorio, tablets y dispositivos móviles). Utilizar CSS Grid/Flexbox, unidades relativas (`rem`, `%`, `vw`/`vh`), `media queries` limpias y contenedores con desplazamiento horizontal controlado (`overflow-x: auto`) para tablas contables extensas.
* **Presupuesto de Recursos:** La instancia objetivo es una **AWS EC2 `t4g.small` (ARM64, 2GB RAM)**. Cada vista debe minimizar el uso de DOM, evitar dependencias externas innecesarias y mantener tiempos de respuesta inmediatos.

---

## 3. Ingesta y Procesamiento de Datos (EBS & RAM Protection)

* **Procesamiento Estricto en Memoria:** Cualquier formulario o endpoint que reciba archivos `.csv` o `.xlsx` **debe procesar el flujo directamente en memoria** utilizando `pandas` (por ejemplo, leyendo desde `request.FILES['file'].file` o `io.BytesIO`).
* **Cero Persistencia de Archivos Temporales en Disco:** Queda prohibido guardar archivos subidos en el sistema de archivos local o en volúmenes EBS (`MediaStorage`). Una vez extraídos, validados y persistidos los registros contables en PostgreSQL, el buffer del archivo debe descartarse inmediatamente (`del`, cierre de buffer) dentro del mismo ciclo de petición.
* **Límite de Carga:** Todo archivo entrante está restringido a un máximo de **5 MB** (`client_max_body_size 5M;` en Nginx y `DATA_UPLOAD_MAX_MEMORY_SIZE` en Django). Se debe validar el tamaño y formato antes de instanciar un `DataFrame` en `pandas`, usando tipos de datos explícitos (`dtype`) y lectura por lotes (`chunksize`) cuando corresponda para proteger los 2 GB de RAM.

---

## 4. Tono del Copywriting

* **Firme, Analítico y Directo:** Los textos de interfaz, etiquetas, mensajes de validación y reportes deben redactarse con precisión técnica y sobriedad contable.
* **Sin Lenguaje Coloquial:** Evitar signos de exclamación, frases condescendientes, humor o adornos innecesarios.
  * *Incorrecto:* `"¡Ups! Algo salió mal al subir tu archivo 😊"`
  * *Correcto:* `"Error de validación: El archivo excede el límite de 5 MB o presenta columnas inválidas."`
