# Levantar el proyecto con la base de datos ya cargada

La base de datos (PostgreSQL) no viaja con el repo de git — te paso el
volcado (`sales_a2_YYYYMMDD.dump`), el archivo `.env` y (si corresponde)
un `.zip` con `media/`, todo por separado.
**Ninguno de estos tres está ni va a estar en git.**

## Qué te tengo que pasar (fuera de git)

- [ ] `sales_a2_YYYYMMDD.dump` (volcado de la base)
- [ ] `.env` (con las credenciales reales)
- [ ] `media.zip` (solo si hay archivos subidos — ver nota en el paso 4.5)
- [ ] Link al repo: **`https://github.com/Isaac26-sq/Proyect_Sales_A2.git`**
  (si tenés guardado el link viejo `Sales_A2`, no lo uses: GitHub redirige
  pero es mejor cloná desde la URL nueva directamente)

## Versiones exactas usadas (para evitar incompatibilidades)

- **Python 3.13.7**
- **PostgreSQL 18.4** (cualquier 18.x debería andar bien; evitá versiones
  más viejas que 18 para el `pg_restore`)

## 1. Instalar PostgreSQL

Instalá **PostgreSQL 18** (misma versión con la que se generó el dump,
para evitar problemas de compatibilidad): https://www.postgresql.org/download/

Durante la instalación anotá la contraseña que le pongas al superusuario
`postgres` — la vas a necesitar en el paso 2.

## 2. Crear una base vacía con el mismo nombre

Abrí una terminal donde esté `psql`/`createdb` (en Windows, normalmente
`C:\Program Files\PostgreSQL\18\bin`) y creá la base vacía. El nombre
tiene que coincidir con `DB_NAME` del `.env` que te paso (`sales_a2`):

```bash
createdb -h localhost -p 5432 -U postgres sales_a2
```

Si el `.env` que te paso usa un usuario distinto a `postgres` (revisá
`DB_USER`/`DB_PASSWORD` ahí), creá ese rol antes o usá el que ya tengas,
siempre que el `.env` apunte a un usuario que exista en tu Postgres local.

## 3. Restaurar el dump

```bash
pg_restore -h localhost -p 5432 -U postgres -d sales_a2 --no-owner --no-privileges -v sales_a2_YYYYMMDD.dump
```

`--no-owner --no-privileges` evita que falle por diferencias de roles
entre tu Postgres local y el mío — el dump ya trae todo (esquema, datos,
secuencias e **historial de migraciones aplicado**).

## 4. Copiar el `.env`

Copiá el `.env` que te paso a la **raíz del proyecto** (mismo nivel que
`manage.py`). Ya viene con `DB_NAME`, `DB_USER`, `DB_PASSWORD` apuntando
a la base que restauraste en el paso 3 — no hace falta que edites nada
ahí salvo que tu usuario/contraseña de Postgres local sean distintos.

El `.env` que te paso trae **todo** lo que el proyecto necesita para
andar sin errores (revisé `config/settings.py` variable por variable):
conexión a la base (`DB_*`), `SECRET_KEY`, `DEBUG`, credenciales de
correo (`EMAIL_*`) y de PayPal sandbox (`PAYPAL_*`). Lo único que
**no** está en `.env` porque el proyecto no lo lee de ahí —
`ALLOWED_HOSTS`, `TIME_ZONE` (`America/Guayaquil`) y el idioma
(`es-ec`) — vienen fijos en `config/settings.py`, así que ya te llegan
correctos con el repo, sin que tengas que configurar nada aparte.

## 4.5. Carpeta `media/` (solo si te paso `media.zip`)

`media/` tampoco viaja en git ni en el dump de la base — la base de datos
solo guarda la *ruta* del archivo (ej. `products/foto.jpg`), no el
archivo en sí. Al momento de armar este instructivo, revisé el contenido
real de `media/` y **ningún producto tiene imagen asignada hoy** (el
único producto que existe en la base no tiene `image` cargado), así que
restaurar el dump sin `media/` **no va a generar links rotos ahora
mismo**. Si te paso `media.zip` de todas formas (por si cargamos
imágenes después, o para no arrancar de cero), descomprimilo en la raíz
del proyecto para que quede `media/products/...` al mismo nivel que
`manage.py`.

## 5. Crear el entorno virtual e instalar dependencias

Usá **Python 3.13** (idealmente 3.13.7, la misma versión con la que se
armó `requirements.txt`, para evitar sorpresas de compatibilidad):

```bash
python --version                  # confirmá que sea 3.13.x
python -m venv ent_sales
ent_sales\Scripts\activate        # Windows
pip install -r requirements.txt
```

## 6. Correr el servidor

```bash
python manage.py runserver
```

## ⚠️ NO corras `python manage.py migrate`

El dump ya incluye la tabla `django_migrations` con **todo el historial
de migraciones ya aplicado** — correr `migrate` de nuevo no debería
romper nada (Django lo detectaría como "ya aplicado"), pero no hace
falta y es una fuente innecesaria de conflictos. Si en algún momento se
agregan migraciones nuevas después de este dump, ahí sí vas a necesitar
correr `migrate` para ponerte al día — te avisamos cuando pase.

Entrá a `http://127.0.0.1:8000/` y logueate con cualquier usuario que ya
exista en la base restaurada (te paso las credenciales aparte, junto con
el `.env`).
