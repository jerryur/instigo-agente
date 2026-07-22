# WhatsApp scooter MVP

Esqueleto del MVP: chat web que simula WhatsApp, un agente con Claude que
recopila datos y clasifica la solicitud, y conexión real a un Odoo de
pruebas (Helpdesk, CRM, Sales) vía External API (XML-RPC).

## Antes de correrlo

1. Duplica tu base de Odoo Custom como entorno de pruebas (odoo.com > Mis
   bases de datos > Duplicar). Confirma que Helpdesk, CRM y Sales estén
   activos ahí.
2. En esa base de pruebas, crea:
   - Equipos de Helpdesk: "Refacciones y Garantías" y "Facturación"
   - Un registro en Configuración > Fuentes de UTM llamado
     "WhatsApp bot (MVP)" (opcional, para trackear el origen en CRM)
   - Unos productos de ejemplo (modelos de scooter) con precio y
     existencia
3. Genera un API key en esa base (Ajustes > tu perfil > Seguridad de la
   cuenta > Nueva clave API).
4. Configura el archivo `.env` (ver sección de abajo).

## Qué es el archivo `.env` y cómo llenarlo

El archivo `.env` es donde se guardan las contraseñas y claves que el
programa necesita para conectarse a Claude y a Odoo. Se guarda aparte del
código por seguridad, para que esos datos nunca queden expuestos si algún
día se sube el proyecto a un repositorio público.

En la carpeta del proyecto ya viene un archivo llamado `.env.example`,
que es una plantilla vacía. Los pasos son:

1. Haz una copia de ese archivo y ponle de nombre `.env` (sin el
   `.example` al final). Si usas la terminal, el comando es:
   ```bash
   cp .env.example .env
   ```
   Si prefieres hacerlo a mano: copia el archivo `.env.example` en la
   misma carpeta y renombra la copia a `.env`.
2. Abre ese nuevo archivo `.env` con cualquier editor de texto simple
   (Bloc de notas, TextEdit, VS Code, etc.) y llena cada línea después
   del signo `=`, sin dejar espacios. Quedan cinco valores por llenar:

   - `ANTHROPIC_API_KEY`: la clave de tu cuenta de Claude/Anthropic. Se
     genera en [console.anthropic.com](https://console.anthropic.com),
     en la sección "API Keys" > "Create Key".
   - `ODOO_URL`: la dirección web de tu base de Odoo de **pruebas** (el
     duplicado que hiciste en el paso 1), por ejemplo
     `https://tu-base-pruebas.odoo.com`.
   - `ODOO_DB`: el nombre técnico de esa misma base de pruebas. Suele
     aparecer en la URL o en la pantalla de selección de bases de datos
     al iniciar sesión en Odoo.
   - `ODOO_USERNAME`: el correo con el que inicias sesión en esa base de
     Odoo.
   - `ODOO_API_KEY`: la clave que generaste en el paso 3 (Ajustes > tu
     perfil > Seguridad de la cuenta > Nueva clave API). Ojo: esto no es
     tu contraseña normal de Odoo, es una clave distinta pensada para
     conectar programas externos.

3. Guarda el archivo. Ya no hay que tocar nada más de código para que
   funcione — el programa lee automáticamente esos valores desde `.env`
   cuando arranca.

Ejemplo de cómo se ve un `.env` ya lleno (con valores inventados, los
tuyos serán distintos):
```
ANTHROPIC_API_KEY=sk-ant-abc123...
ODOO_URL=https://tienda-scooters-pruebas.odoo.com
ODOO_DB=tienda-scooters-pruebas
ODOO_USERNAME=api@tiendascooters.com
ODOO_API_KEY=9f8e7d6c5b4a...
```

## Correr local

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)   # o usa python-dotenv si prefieres
uvicorn main:app --reload
```

Abre `http://localhost:8000` y chatea con el bot como si fuera WhatsApp.

## Desplegar en Render

1. Sube esta carpeta a un repo de GitHub.
2. En Render: New > Web Service, conecta el repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Agrega las variables de entorno de `.env.example` en Render >
   Environment.

## Qué falta para producción (fuera de este MVP)

- Cambiar el chat falso por el webhook real de WhatsApp Cloud API (la
  lógica de `claude_agent.py` y `odoo_client.py` no cambia).
- Guardar el estado de sesión en algo persistente (Redis/DB) en vez de
  memoria del proceso.
- Subir el video real a un storage y pasar la URL a Odoo en vez de solo
  el nombre del archivo.
- Manejo de errores y reintentos en las llamadas a Odoo.
