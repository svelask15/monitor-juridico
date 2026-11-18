# Monitor jurídico (SCJN · Semanario Judicial · DOF)

Programa en Python que todos los días revisa fuentes oficiales y te avisa por
correo y/o Telegram de lo nuevo. Funciona con reglas fijas, sin IA.

| Fuente | Qué obtiene | Cómo |
|---|---|---|
| **DOF** (SIDOF) | Todo lo publicado (matutina, vespertina, extraordinaria), clasificado: reformas constitucionales, leyes nuevas, reformas legales, sentencias y acuerdos de la SCJN, etc. | API JSON oficial `sidof.segob.gob.mx` |
| **Semanario Judicial** | Tesis y jurisprudencias nuevas de la Duodécima Época, con rubro, clave, precedente y votos. Marca las que **interrumpen, sustituyen o dejan sin efectos** criterios anteriores. | API pública del sitio `sjf2.scjn.gob.mx` |
| **Comunicados SCJN** | Lo que resolvió el Pleno en cada sesión: asuntos (AI, CC, ADR…), fecha de sesión y votaciones mencionadas. | Lectura del HTML de cada comunicado |

Cada día genera `reportes/AAAA-MM-DD.md` y los domingos `reportes/semana-AAAA-MM-DD.md`.
Todo lo detectado se guarda también en `data/historico/` (eso servirá para la página web de la fase 2).

---

## Instalación en GitHub (gratis, corre solo)

1. **Crea una cuenta en GitHub** (github.com) si no tienes.
2. **Crea un repositorio nuevo** → nombre `monitor-juridico` → *Private* → Create.
3. **Sube los archivos**: en el repositorio, *Add file → Upload files* y arrastra
   todo el contenido de esta carpeta (incluida la carpeta oculta `.github`; si tu
   explorador no la muestra, créala a mano con *Add file → Create new file* y el
   nombre `.github/workflows/monitor.yml`, pegando el contenido).
4. **Configura dónde recibir los avisos** en *Settings → Secrets and variables →
   Actions → New repository secret*:

   **Correo (Gmail):**
   - `CORREO_REMITENTE` → tu correo de Gmail
   - `CORREO_CONTRASENA` → una *contraseña de aplicación* (no tu contraseña normal):
     myaccount.google.com → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones
   - `CORREO_DESTINO` → a dónde llega (puede ser el mismo)

   **Telegram (opcional, llega al celular):**
   - En Telegram habla con **@BotFather** → `/newbot` → copia el token → secreto `TELEGRAM_TOKEN`
   - Mándale cualquier mensaje a tu bot, abre
     `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia el número de `"chat":{"id":…}`
     → secreto `TELEGRAM_CHAT_ID`
5. **Pruébalo**: pestaña *Actions* → *Monitor jurídico* → *Run workflow*.
   La primera corrida crea la base (registra las tesis existentes y te muestra
   solo una muestra de las más recientes). Desde la segunda, solo avisa de lo nuevo.

Horario: todos los días ~20:37 (hora de CDMX) y el resumen semanal los domingos ~9:13.
Para cambiarlo edita las líneas `cron` en `.github/workflows/monitor.yml`.

## Ajustes (archivo `config.yaml`)

- `dof.prioridad_maxima`: qué tanto del DOF quieres ver (1 = solo lo esencial … 4 = todo).
- `dof.palabras_clave`: leyes o temas que siempre quieres ver.
- `semanario.instancias`: `["Pleno"]` solo SCJN; agrega `"Plenos Regionales"` o pon `["todas"]`
  para incluir Tribunales Colegiados.

## Correrlo en tu computadora

```bash
pip install -r requirements.txt
python run.py --sin-enviar          # revisión diaria, imprime el reporte
python run.py --solo dof            # solo una fuente
python run.py --semanal --sin-enviar
python -m unittest discover tests   # pruebas
```

## Límites conocidos (léelos)

- **La API del Semanario no es oficial ni está documentada.** La SCJN puede cambiarla
  y su firewall a veces bloquea servidores de la nube (como los de GitHub). Si pasa,
  el reporte lo dice en "Fuentes que no se pudieron revisar" y las demás fuentes siguen
  funcionando. Solución: correrlo desde tu computadora o ajustar `monitor/sjf.py`.
- **"Dejó de estar vigente" se detecta por palabras** (interrupción, sustitución,
  "queda sin efectos", contradicción de criterios…). Es una alerta para que revises,
  no una conclusión jurídica.
- Los comunicados solo traen las votaciones cuando el texto las menciona. Para votos
  particulares completos, el reporte incluye los votos asociados a cada tesis y la liga
  al Semanario.
- El `id_inicial` de comunicados (8545) corresponde al 31/ago/2026; el programa avanza
  solo a partir de ahí.

## Estructura

```
run.py                  # punto de entrada
config.yaml             # tus preferencias
monitor/dof.py          # DOF vía SIDOF
monitor/sjf.py          # Semanario Judicial + reglas de vigencia
monitor/comunicados.py  # comunicados del Pleno
monitor/clasificar.py   # reglas de clasificación del DOF
monitor/reporte.py      # arma el boletín
monitor/notificar.py    # correo y Telegram
data/                   # memoria entre corridas (no borrar)
reportes/               # boletines generados
```
