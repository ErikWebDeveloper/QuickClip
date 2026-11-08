# AGENTS.md - Creador de Editor de Video de Escritorio (Ubuntu / Estilo Kick o Vice)

Este documento define las directrices, la arquitectura y los requisitos técnicos para que el agente de IA desarrolle un editor de video de escritorio minimalista, rápido y optimizado para Ubuntu, enfocado en el corte rápido de clips.

---

## 1. Visión General del Proyecto
- **Nombre provisional:** QuickClip Editor (o el que se defina).
- **Plataforma principal:** Ubuntu (Linux).
- **Lenguajes preferentes:** 
  - Backend/Procesamiento: Python (con `ffmpeg-python` o llamadas directas a `ffmpeg`) o Node.js (`fluent-ffmpeg`).
  - Interfaz de Gráfica (GUI): Electron + React (si se usa Node) o PyQt6 / CustomTkinter (si se usa Python). Se recomienda **Python + PyQt6 + FFmpeg** por rendimiento nativo en Linux con manejo de video.
- **Filosofía:** Interfaz limpia, oscura, moderna (estilo Kick/Vice), sin curvas de aprendizaje complejas: abrir, recortar y exportar en segundos.

---

## 2. Requisitos Funcionales

### A. Explorador de Archivos Integrado
- La aplicación debe incluir una vista de árbol o explorador de archivos propio dentro de la interfaz para navegar por las carpetas del sistema (enfocado en directorios de video comunes en Ubuntu como `~/Videos` o `~/Captures`).
- Permitir arrastrar y soltar (Drag & Drop) un archivo de video directamente al área de trabajo.

### B. Línea de Tiempo y Previsualización de Fotogramas (Scrubbing Visual)
- Al arrastrar los controladores de la zona de corte (inicio y fin), la interfaz debe generar o extraer **fotogramas clave en miniatura (thumbnails)** en tiempo real a lo largo de la línea de tiempo para guiar visualmente al usuario en el corte exacto.
- Reproductor de video integrado básico (Play/Pause, barra de progreso, indicador de tiempo actual).

### C. Sistema de Guardado Inteligente
Una vez que el usuario selecciona el clip y pulsa exportar/recortar:
1. **Comprobación de Existencia:** Si el archivo de salida ya existe con el mismo nombre, mostrar un modal de advertencia nativo/estilizado que pregunte:
   - *¿Sobrescribir el archivo existente?*
   - *¿Crear uno nuevo (auto-incrementar sufijo, ej. `video_01.mp4`)?*
2. **Renombrado en línea:** Permitir editar el nombre del archivo de salida directamente antes de confirmar la exportación.

---

## 3. Arquitectura Técnica Sugerida (Stack Python)

Si se implementa con Python:
- **GUI:** `PyQt6` (ofrece excelente rendimiento y soporte de estilos mediante QSS).
- **Procesamiento de Video:** `FFmpeg` instalado en el sistema operativo Ubuntu (`sudo apt install ffmpeg`).
- **Extracción de Fotogramas:** Generación de fotogramas de baja resolución en segundo plano mediante hilos (`QThread`) para mantener la interfaz fluida mientras se arrastra el corte.

---

## 4. Instrucciones Paso a Paso para la IA (Fases de Desarrollo)

### Fase 1: Estructura Base y UI (Estilo Kick/Vice)
- [ ] Crear la ventana principal con paleta de colores oscura (tonos negros, grises oscuros y acentos en verde neón o violeta característicos).
- [ ] Implementar el panel izquierdo con el **Explorador de Archivos** local de Ubuntu.
- [ ] Implementar el panel central con el reproductor de video y la línea de tiempo interactiva.

### Fase 2: Motor de Previsualización de Fotogramas
- [ ] Conectar la carga del video a un proceso secundario que extraiga miniaturas temporales en caché.
- [ ] Dibujar las miniaturas en la barra de la línea de tiempo para que el usuario vea los fotogramas al mover los tiradores de selección (In/Out).

### Fase 3: Lógica de Recorte con FFmpeg
- [ ] Programar un corte siempre preciso al fotograma, sin selector de modo: re-codificación H.264 de alta calidad, audio original cuando el contenedor lo permita y seek con pre-roll para mantener exactitud y timestamps correctos.

### Fase 4: Diálogo de Gestión de Archivos (Sobrescribir / Renombrar / Nuevo)
- [ ] Crear el modal de guardado que valide si el archivo destino ya existe.
- [ ] Implementar las opciones de **Sobrescribir** o **Crear nuevo** con nomenclatura automática o personalizada.

---

## 5. Criterios de Éxito y Rendimiento
- **Fluidez:** El desplazamiento por la línea de tiempo no debe generar tirones (*lag*).
- **Compatibilidad Ubuntu:** Uso correcto de rutas de Linux (`/home/...`) y verificación automática de que `ffmpeg` esté presente en el sistema.
