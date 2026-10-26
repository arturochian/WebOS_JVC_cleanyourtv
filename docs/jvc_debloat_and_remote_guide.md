# Guía Detallada de Optimización, Desbloqueo y Control Remoto para JVC con LG webOS Hub

Esta guía proporciona instrucciones técnicas paso a paso para configurar, optimizar y controlar televisores **JVC Smart TV con LG webOS Hub** (específicamente validado en el modelo **JVC LT-32KB116**).

---

## 1. Particularidades del Hardware JVC LT-32KB116

A diferencia de los televisores LG propios (como las series C o G OLED), los televisores manufacturados por socios licenciatarios de **LG webOS Hub** presentan especificaciones particulares:

| Característica | Especificación en JVC LT-32KB116 |
| :--- | :--- |
| **SoC / Procesamiento** | Chipset de bajo consumo optimizado para paneles HD/FHD de 32" |
| **Aceleración Gráfica** | Soporte para aceleración por hardware CSS en propiedades `transform` y `opacity` |
| **Control Remoto** | Control estándar JVC (Infrarrojo / Bluetooth) con teclado numérico (0-9) y cruceta D-pad, **sin giroscopio Magic Remote** ni rueda de desplazamiento |
| **Puertos de Red** | Wi-Fi 2.4/5 GHz y puerto Ethernet RJ-45 |
| **Puertos de Servicio** | SSAP WebSocket (`wss://<IP>:3001`) y SSH Developer Mode (`puerto 9922`) |

---

## 2. Configuración del Atajo de Acceso Rápido (Quick Access) en el Control JVC

Dado que el control remoto de JVC no cuenta con el puntero flotante de LG, la forma más rápida y cómoda de acceder al launcher estilo Apple TV es mediante la función de hardware **Quick Access**:

### Instrucciones de Mapeo del Botón 1:

1. **Instalar y Ejecutar**: Asegúrate de haber desplegado la aplicación mediante `.\install.ps1 -TvHost <IP_DE_TU_TV>`.
2. **Abrir el Launcher**: Abre la aplicación `Home` (`com.gathin.tvhome`) en la TV.
3. **Mantener Presionado**: Con la pantalla del launcher visible, apunta el control remoto JVC al televisor y **mantén presionado el botón numérico `1` durante 3 segundos**.
4. **Confirmación Visual**: Aparecerá un mensaje flotante en la esquina superior derecha:
   > *"Quick Access: Aplicación asignada al botón 1"*
5. **Uso Diario**:
   - Para abrir tu launcher limpio en cualquier momento: **Mantén presionado el botón `1` por 1.5 segundos**.
   - Funciona desde cualquier entrada HDMI (consolas de videojuegos, decodificadores, PC) o mientras miras televisión en vivo.

### Tabla de Teclas del Control Remoto JVC:

| Tecla Física | Código JavaScript (`keyCode`) | Función en el Launcher |
| :--- | :---: | :--- |
| **Flecha Izquierda** | `37` | Mueve el foco hacia la tarjeta izquierda en el dock |
| **Flecha Arriba** | `38` | Sube a la barra superior / fila de ajustes |
| **Flecha Derecha** | `39` | Mueve el foco hacia la tarjeta derecha en el dock |
| **Flecha Abajo** | `40` | Baja a la fila de aplicaciones o dock secundario |
| **Botón OK / Enter** | `13` | Lanza la aplicación o entrada seleccionada |
| **Botón Back / Atrás** | `461` | Regresa al dock principal o cierra el diálogo |
| **Botón Exit** | `514` | Cierra la aplicación web |

---

## 3. Navegación por Menús para Desbloqueo de Publicidad (Debloating)

El sistema LG webOS Hub incluye por defecto varias filas patrocinadas y recolección de datos de telemetría. Sigue estos pasos para desactivarlos:

### A. Eliminar Promociones de la Pantalla de Inicio
1. Presiona el botón **Ajustes** (ícono de engranaje) en el control remoto.
2. Selecciona **Todos los Ajustes** -> **General** -> **Configuración de Inicio**.
3. Cambia la opción **Promoción de Inicio (Home Promotion)** a **DESACTIVADO (OFF)**.
   - *Efecto*: Elimina los banners publicitarios comerciales en la parte superior.

### B. Desactivar Recomendaciones de Contenido
1. En el mismo menú **Configuración de Inicio**:
2. Cambia la opción **Recomendación de Contenido (Content Recommendation)** a **DESACTIVADO (OFF)**.
   - *Efecto*: Oculta la fila de programas sugeridos y promociones de servicios de streaming no suscritos.

### C. Configurar Encendido Directo en Entrada Reciente
1. En el mismo menú **Configuración de Inicio**:
2. Selecciona **Estado al Encender (Power On Status)**.
3. Cambia de *Pantalla de Inicio* a **Entrada Reciente (Recent Input)**.
   - *Efecto*: Al encender la TV, cargará de inmediato la última entrada activa (HDMI 1, HDMI 2 o TV), evitando la pantalla pesada de fábrica y acelerando el encendido.

### D. Revocar Telemetría y Reconocimiento Automático de Contenido (ACR)
1. Ve a **Todos los Ajustes** -> **General** -> **Soporte** -> **Acuerdos de Usuario**.
2. Desmarca las siguientes opciones opcionales:
   - **Información de Visualización**: Evita que LG analice qué contenido se reproduce en pantalla.
   - **Publicidad Basada en Intereses**: Desactiva el identificador de publicidad dirigida.
3. Guarda los cambios.

---

## 4. Mantenimiento del Modo Desarrollador (Developer Mode)

La sesión del Developer Mode de LG tiene una duración por defecto de **999 horas**. Para mantenerla activa:

1. **Renovación Automática**: Si mantienes la app Developer Mode en la TV y abres la aplicación ocasionalmente, puedes hacer clic en **Extend** para renovar el temporizador a 999 horas adicionales.
2. **Key Server**: Asegúrate de que la opción **Key Server** esté siempre en **ON** dentro de la app Developer Mode en la TV si deseas realizar nuevas sincronizaciones desde tu PC con Windows.
