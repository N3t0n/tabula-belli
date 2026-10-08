# TABULA BELLI – MANUAL DE INSTALACIÓN

Proyecto Fin de Ciclo – Desarrollo de Aplicaciones Web
Autor: José Miguel Paredes Báez

Este documento describe, paso a paso, cómo instalar y ejecutar **Tabula Belli**
en un entorno local a partir de un checkout o snapshot limpio, y cómo recuperar
el entorno en caso de que falte algún fichero o se quiera recrear la base de
datos desde cero.

---

## 1. Requisitos del sistema

Tabula Belli está pensada para ejecutarse en un entorno de desarrollo local típico de aplicaciones Django:

* **Sistema operativo:** Windows / macOS / Linux
* **Python:** 3.12 (runtime actualmente soportado y validado)

  **IMPORTANTE:** Python debe estar instalado en su sistema antes de comenzar con la instalación de Tabula Belli.

  Descargue el instalador desde la página oficial:
  
  **<https://www.python.org/downloads/>**
  
  Instale Python 3.12 siguiendo el asistente de instalación.
  
  **Nota importante para Windows:** Durante la instalación, asegúrese de marcar la casilla "Add Python to PATH" para poder ejecutar Python desde cualquier terminal.

  Tras la instalación, puede comprobar que todo es correcto ejecutando:

  ```bash
  python --version
  ```

  o, en algunos sistemas:

  ```bash
  python3 --version
  ```

  La salida debe mostrar Python 3.12.x.

* **Navegador web moderno:** Chrome, Firefox, Edge, Safari
* **Editor de código (opcional):** Visual Studio Code, PyCharm, etc.

Para generar los assets de frontend:

* **Node.js:** 24.14.0 con `npm`, versión validada y declarada en `.node-version`
* **PostgreSQL:** 16.x, con cliente `psql` y un servidor accesible
* **Conexión a Internet:** necesaria para instalar dependencias. Las ubicaciones
  se cargan desde el catálogo fijo incluido; no requieren descarga durante la instalación.

La aplicación utiliza:

* **Django** como framework web
* **PostgreSQL** como único backend de base de datos soportado
* **Tailwind CSS, HTMX y Alpine.js** para el frontend
* **django-allauth** para autenticación
* **django-cities-light** para datos de localización
* **python-decouple** para la configuración a través de variables de entorno

---

## 2. Opción A – Puesta en marcha desde un checkout limpio (recomendada)

Es la opción recomendada para la evaluación del proyecto. 

### 2.1. Preparar el directorio del proyecto

1. Clonar el repositorio o extraer el snapshot en una carpeta de trabajo, por
   ejemplo:

   * Windows: `C:\Users\Profesor\Desktop\tabula_belli`
   * Linux/macOS: `/home/profesor/tabula_belli`
   
2. Abrir una terminal en esa carpeta, o usar la terminal integrada de un editor:

```bash
# Windows PowerShell
cd C:\Users\Profesor\Desktop\tabula_belli

# Linux / macOS
cd /home/profesor/tabula_belli
```

### 2.2. Verificar archivos críticos

Comprobar que existen los siguientes ficheros (desde la raíz del proyecto):

* `.env.example`
* `requirements.txt`
* `package.json`
* `package-lock.json`
* `src/static/css/input.css`

Puede verificarlos desde la terminal con:

```powershell
# Windows PowerShell
Test-Path .env.example, requirements.txt, package.json, package-lock.json, src/static/css/input.css
```

```bash
# Linux / macOS
ls -l .env.example requirements.txt package.json package-lock.json src/static/css/input.css
```

Todos los archivos deben existir. El checkout limpio no incluye `.env`: créelo
desde la plantilla versionada antes de ejecutar Django.

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

Abra `.env`, sustituya todos los valores `REPLACE_WITH_...` y no comparta ni
versione el resultado. La generación de `SECRET_KEY` se completa en la sección
2.5, una vez instalado Django.

### 2.3. Crear entorno virtual

```bash
python -m venv .venv
```

### 2.4. Activar entorno virtual mediante uno de los siguientes métodos

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

Al activarse correctamente, el prompt mostrará algo similar a `(.venv)` al inicio.

### 2.5. Instalar dependencias

```bash
python -m pip install -r requirements.txt
```

Esto instalará Django, django-allauth, django-anymail, django-cities-light,
django-htmx, python-decouple, requests y el resto de dependencias necesarias.

`requirements.in` documenta las dependencias directas de la aplicación, mientras
que `requirements.txt` fija todas las versiones resueltas para que instalaciones
distintas obtengan el mismo entorno. El proyecto utiliza `pip`; no requiere
Pipenv, Poetry ni otro gestor de dependencias.

Genere una `SECRET_KEY` distinta para esta instalación:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copie el valor resultante en `SECRET_KEY` dentro de `.env` y compruebe que
también ha sustituido los placeholders `DB_NAME`, `DB_USER` y `DB_PASSWORD`.

### 2.6. Crear role y base PostgreSQL

Los nombres son orientativos. El role necesita `CREATEDB` para que Django pueda
crear y destruir su base temporal de tests:

```bash
sudo -u postgres createuser --login --createdb --pwprompt tabula_belli_app
sudo -u postgres createdb --owner=tabula_belli_app tabula_belli_db
```

En sistemas sin `sudo`, ejecuta las operaciones equivalentes con un usuario
administrador de PostgreSQL. Comprueba la conexión:

```bash
psql -h localhost -U tabula_belli_app -d tabula_belli_db
```

Confirme que las credenciales creadas coinciden con `DB_NAME`, `DB_USER` y
`DB_PASSWORD` en `.env`. La contraseña sólo debe existir en ese archivo local
ignorado.

### 2.7. Generar assets frontend

Desde la raíz del proyecto:

```bash
npm ci
npm run build
```

El build compila Tailwind CSS y copia HTMX, Alpine.js y Flowbite desde las
versiones fijadas en `package-lock.json`. Los archivos generados no se versionan.

### 2.8. Preparar el esquema y los datos

Desde la raíz:

```bash
python src/manage.py migrate
python src/manage.py loaddata fixtures/locations/europe-2026-10-06.json.gz
python src/manage.py seed_games
python src/manage.py seed_users
python src/manage.py seed_events --seed 20250809
python src/manage.py seed_registrations --seed 20250809
```

La carga usa el catálogo fijo GeoNames de 2026-10-06, sin descargar datos.
Consultar `fixtures/locations/README.md` y `manifest.json`. Cargar únicamente en
una base nueva con tablas de ubicaciones vacías; no superponerlo al catálogo
de producción. `load_cities` queda para actualizaciones deliberadas en una base separada. Sin `--base-date`, `seed_events` usa la fecha local actual para crear
una demo util en el momento de la instalación. Puede pasar una fecha explícita
con `--base-date YYYY-MM-DD` para fijar el calendario de eventos, pero
`seed_registrations` selecciona únicamente ventanas abiertas en la hora real de
ejecución y su conteo puede variar.

### 2.9. Navegar a la carpeta `src`

```bash
cd src
```

### 2.10. Arrancar el servidor de desarrollo

```bash
python manage.py runserver
```

### 2.11. Abrir la aplicación en el navegador

* URL principal: `http://localhost:8000/`

Debería mostrarse el 'Home' de Tabula Belli.

### 2.12. Credenciales de acceso

El proyecto no incluye un superusuario predefinido. Para acceder a Django Admin,
crea credenciales locales propias desde la carpeta `src/`:

```bash
python manage.py createsuperuser
```

Después utiliza el usuario creado en `http://localhost:8000/admin/`.

**Usuario jugador (ejemplo):**

* Usuario: `rogal_dorn`
* Contraseña: `TestPass123!`
* URL login: `http://localhost:8000/accounts/login/`

Otros jugadores disponibles (todos con contraseña `TestPass123!`), por ejemplo:

* `horus_lupercal`
* `roboute_guilliman`
* `lion_eljonson`
* `magnus_the_red`
* `leman_russ`
* … (hasta un total de 18 jugadores)

### 2.13. Pruebas básicas recomendadas

Pruebas rápidas tras la instalación:

1. **Como usuario anónimo:**
   * Ver la página de inicio.
   * Navegar a la lista de eventos.
   * Aplicar algún filtro (por juego o ubicación).
   * Ver el detalle de un evento.

2. **Como jugador (`rogal_dorn`):**
   * Iniciar sesión con `rogal_dorn` / `TestPass123!`.
   * Registrarse en un evento con estado `OPEN`.
   * Ver la pestaña correspondiente en "My Events".
   * Cerrar sesión.

3. **Como administrador local:**
   * Crear un usuario con `python manage.py createsuperuser` si todavía no existe.
   * Iniciar sesión con las credenciales elegidas durante ese proceso.
   * Acceder a `/admin/`.
   * Revisar modelos (usuarios, juegos, eventos, inscripciones).
   * Editar un evento y comprobar el cambio en el frontend.

---

## 3. Opción B – Recuperar o recrear el entorno si algo falla

Esta opción cubre los casos en los que:

* Falta `.env`.
* Falta la configuración PostgreSQL o se quiere empezar con una base vacía.
* Faltan los assets frontend generados y la interfaz se ve sin estilos.

Se recomienda solo si la **Opción A** no funciona o si se desea comprobar la capacidad de reproducción completa del entorno.

### 3.1. Crear o regenerar `.env`

El checkout limpio incluye `.env.example`, no `.env`. Restaure la configuración
local copiando siempre la plantilla versionada:

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

Genere un valor distinto para cada instalación con una utilidad estándar de
Django y sustituya `SECRET_KEY` sin compartir ni versionar el resultado:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Sustituya también todos los placeholders `REPLACE_WITH_...`, especialmente las
credenciales PostgreSQL, antes de ejecutar cualquier comando de Django.

### 3.2. Generar frontend

Los outputs frontend se regeneran siempre desde las fuentes versionadas y el lock
de npm:

```bash
# Desde la raíz del proyecto (donde está package.json)
npm ci
npm run build
```

Este proceso:

* Compila Tailwind CSS a `src/static/css/output.css`.
* Copia HTMX, Alpine.js y Flowbite a `src/static/js/`.

`staticfiles/` no es una fuente y no se versiona. Cuando se necesite preparar el
directorio de despliegue de Django, se genera con:

```bash
python src/manage.py collectstatic --noinput
```

### 3.3. Preparar PostgreSQL desde cero

Con una base PostgreSQL vacía cuyo propietario sea el role de la aplicación:

1. Asegurarse de que el entorno virtual está activado y las dependencias instaladas.
2. Navegar a `src`:

```bash
cd src
```

3. Ejecutar migraciones:

```bash
python manage.py migrate
```

4. Cargar datos de localizaciones:

```bash
python manage.py loaddata ../fixtures/locations/europe-2026-10-06.json.gz
```

Este comando carga el catálogo fijo incluido, sin conexión a Internet. Usarlo solo al preparar una base nueva, con tablas de ubicaciones vacías; no sobre el catálogo de producción. Ver `fixtures/locations/README.md`.

5. Cargar catálogo de juegos:

```bash
python manage.py seed_games
```

6. Crear usuarios de prueba:

```bash
python manage.py seed_users
```

Este comando crea únicamente jugadores sintéticos no privilegiados. Si se necesita
acceso administrativo local, se debe ejecutar `python manage.py createsuperuser`.

7. Crear eventos de ejemplo:

```bash
python manage.py seed_events --seed 20250809
```

8. Crear inscripciones:

```bash
python manage.py seed_registrations --seed 20250809
```

Esta receta usa la fecha local actual para mantener eventos utilizables. Si se
usa `--base-date YYYY-MM-DD`, el calendario de eventos queda fijado, pero el
número de inscripciones sigue dependiendo de qué ventanas estén `OPEN` en la
hora real de ejecución.

El **orden de ejecución es importante** y debe respetarse tal como se indica arriba.

Una vez completados estos pasos, se puede lanzar de nuevo:

```bash
python manage.py runserver
```

### 3.4. Ejecutar tests

Desde la raíz, con PostgreSQL disponible, el role autorizado para crear bases y
el entorno virtual activado, ejecute la variante de su terminal:

```powershell
# Windows PowerShell
$env:DEBUG = "False"
python src/manage.py test -v 2
```

```bat
:: Windows CMD
set DEBUG=False
python src/manage.py test -v 2
```

```bash
# Linux / macOS
DEBUG=False python src/manage.py test -v 2
```

---

## 4. Runtime mínimo de producción

Producción usa el mismo `settings.py` con `DJANGO_ENV=production`. Configura una
`SECRET_KEY` propia, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, todas las variables
`DB_*`, `DEFAULT_FROM_EMAIL`, `RESEND_API_KEY` y `FORMSPREE_FORM_ID`.

En desarrollo, los emails transaccionales de cuenta de django-allauth usan el
backend de consola y se muestran en la terminal. No se requiere `RESEND_API_KEY`
ni `FORMSPREE_FORM_ID` para trabajar localmente; si Formspree no esta
configurado, la pagina Contact se renderiza con el envio deshabilitado.

En produccion, los emails transaccionales de django-allauth usan Resend por API
HTTPS mediante django-anymail. El formulario Contact se envia directamente a
Formspree desde el navegador y es independiente de los emails de cuenta. No se
usa SMTP en produccion.

Prepara y valida el despliegue:

```bash
npm ci
npm run build
python src/manage.py collectstatic --noinput
python src/manage.py check --deploy
```

Arranca Gunicorn desde la raíz:

```bash
gunicorn --chdir src config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
```

WhiteNoise sirve `staticfiles/` directamente desde Django. En producción están
activos HTTPS redirect, cookies seguras, HSTS y el header de proxy SSL. El proxy
debe enviar `X-Forwarded-Proto: https`. No es necesario añadir Nginx, CDN ni un
servicio externo para esta configuración mínima.

El endpoint `GET /health/` responde HTTP 200 con una respuesta mínima y no
depende de datos demo. Puede utilizarse como healthcheck HTTP del proveedor.

### Restauración periódica de la demo

Configura **solo en el job de reinicio** `DEMO_RESET_ALLOWED=True`,
`DEMO_RESET_DATABASE_NAME` con el
nombre exacto de la PostgreSQL de la demo y las tres variables privadas
`DEMO_ADMIN_USERNAME`, `DEMO_ADMIN_EMAIL` y `DEMO_ADMIN_PASSWORD`. No reutilices
estas credenciales en otras cuentas ni las guardes en Git.

El scheduler del proveedor ejecutará normalmente:

```bash
python src/manage.py reset_demo --confirm
```

El mismo comando puede ejecutarse manualmente cuando sea necesario. Es una
operación destructiva: elimina Events, Registrations, usuarios y Games de la
demo, conserva Locations, reconstruye el dataset determinista y crea al final
el admin privado. El comando se niega a actuar sin el flag, la confirmación, el
nombre exacto de la base y toda la configuración del admin.

#### Mantenimiento automático y fallos

El comando activa mantenimiento al adquirir un bloqueo de PostgreSQL. Las
peticiones que ya estaban procesándose terminan antes de borrar datos; si no
terminan en 30 segundos, el reinicio se aborta sin borrar nada. Las nuevas
peticiones reciben una página de mantenimiento HTTP 503, `Retry-After: 60` y
`Cache-Control: no-store`. Los archivos estáticos y `/health/` siguen disponibles.
El job `complete_past_events` omite esa ejecución y vuelve a intentarlo en su
siguiente intervalo. Dos reinicios no pueden ejecutarse simultáneamente.

El mantenimiento se libera después del commit o rollback. Si el proceso se
termina, PostgreSQL libera los bloqueos al cerrar su conexión; no queda un flag
persistente que deba desactivarse a mano. No hace falta pausar ni reactivar el
servicio en Northflank. Una pérdida de conexión debe ser detectada por PostgreSQL
antes de liberar la sesión. Usa una conexión directa al addon PostgreSQL, no un
pooler en modo transaction: estos bloqueos pertenecen a la sesión.

Antes de activar un calendario, verifica que **web, complete-past-events y
reset-demo usan la versión con esta protección y la misma base PostgreSQL**.
Mantén `DEMO_RESET_ALLOWED=False` y sin credenciales administrativas de reset en
la web y en el job de eventos. En Northflank el grupo privado de reset debe
estar restringido exclusivamente a `reset-demo`; no habilites ejecución con
cada nueva imagen. Mantén retries 0 y un timeout de 600 segundos. Comprueba el
resultado de cada ejecución en los logs: un fallo revierte los cambios y
conserva el dataset anterior, pero requiere corregir su causa antes de reintentar.

Northflank interpreta el cron en UTC. Por ejemplo, `0 5 6 2,4,6,8,10,12 *`
significa el día 6 de los meses pares a las 05:00 UTC. No equivale a las 05:00
locales de Europa: el cambio de hora modifica la equivalencia. El calendario
definitivo debe elegirse y comprobarse en el proveedor antes de activarlo.

Para probar localmente no necesitas Northflank ni programar un reset. Sigue la
instalación con el catálogo fijo y los seeds; para acceso administrativo propio
usa `python src/manage.py createsuperuser`. Los correos locales se imprimen en
consola. Si quieres comprobar también el reset destructivo, configura las
variables anteriores en un entorno **desechable** con el nombre exacto de esa
base, ejecuta el comando y deja de nuevo `DEMO_RESET_ALLOWED=False`. No copies
credenciales ni bases de producción para probar el proyecto.

### 4.1. Contrato obligatorio del scheduler de eventos

**REQUIRED BEFORE FINAL DEPLOYMENT**

Los eventos `ACTIVE` cuya fecha `end_at` ya ha pasado deben persistirse como
`COMPLETED` mediante el management command existente:

```bash
python src/manage.py complete_past_events
```

Todo deployment de produccion debe configurar **una unica ejecucion periodica
efectiva** de este comando. La frecuencia recomendada es **cada 5 minutos**, que
limita a ese intervalo el tiempo durante el que un estado persistido puede quedar
desactualizado sin generar una carga operativa innecesaria.

El comando selecciona unicamente eventos `ACTIVE` ya terminados, reutiliza el
servicio de lifecycle aprobado y es idempotente. Una segunda ejecucion no vuelve
a modificar eventos ya completados. Los listados y otras peticiones GET no
ejecutan este mantenimiento ni escriben estados en la base de datos.

Este repositorio prepara el contrato provider-neutral; no instala ni configura
cron, systemd timers, Celery, Redis ni un scheduler especifico. La integracion
concreta se realizara cuando se elija el proveedor de hosting:

```text
Contrato preparado ahora != Scheduler real desplegado
```

Mientras el job real no exista y no haya sido validado, el deployment esta
preparado tecnicamente pero no cerrado operacionalmente.

**MANDATORY FINAL DEPLOYMENT CHECK**

- Configurar un scheduler/job real en el proveedor elegido.
- Usar exactamente `python src/manage.py complete_past_events`.
- Programar una unica ejecucion efectiva cada 5 minutos.
- Confirmar que el job se ejecuta automaticamente.
- Crear o identificar un evento de prueba `ACTIVE` con `end_at` pasado.
- Comprobar su transicion persistida a `COMPLETED`.
- Verificar que ninguna peticion GET es necesaria para la transicion.
- Verificar que los logs del job son visibles.
- Provocar de forma controlada un fallo y comprobar que es detectable.
- Confirmar que no existen schedulers duplicados.
- Documentar la configuracion especifica del proveedor.

### 4.2. Integración continua

El workflow `.github/workflows/ci.yml` se ejecuta en pushes y pull requests.
Valida Python 3.12, PostgreSQL 17.11, Node desde `.node-version`, dependencias,
tests, build frontend, `collectstatic`, `check --deploy` y que los comandos no
dejen cambios versionados.

---

## 5. Datos de ejemplo incluidos en la base de datos

La carga validada actualmente contiene:

* **43 países** europeos.
* Las regiones y ciudades europeas disponibles en la fuente GeoNames actual.
  En la carga comprobada había 948 regiones, pero este conteo externo puede
  cambiar cuando GeoNames actualice sus datos.
* **123 juegos**:
  * 25 TCGs (Trading Card Games).
  * 48 TTRPGs (Tabletop RPGs).
  * 50 wargames.
* **18 usuarios jugadores** (sin superusuario predefinido).
* **1.010 eventos**. El seed asigna el estado persistido `ACTIVE` o `COMPLETED`
  según la fecha de finalización; no genera eventos `CANCELED`. `OPEN` es un
  estado calculado de la ventana de registro, no un estado persistido del evento.
* Un número variable de inscripciones, limitado a eventos cuya ventana de
  registro esté `OPEN` en la hora real de ejecución. La carga validada el
  2026-08-12 produjo 628, pero no se promete ese conteo para otras fechas.

Este volumen de datos permite probar el comportamiento de filtros, listados, panel "My Events" y flujos de inscripción/cancelación de forma realista.

---

Con estos pasos, cualquier persona que reciba un checkout o snapshot limpio de
Tabula Belli puede:

1. Instalarlo y arrancarlo sin dificultad.
2. Reproducir los datos de ejemplo o regenerarlos desde cero.
3. Verificar, a través de pruebas basadas en los casos de uso, que la aplicación funciona como se documenta.
4. Entender qué contiene el proyecto y qué se excluye por ser específico del entorno local.
