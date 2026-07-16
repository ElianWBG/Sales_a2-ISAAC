# Levantar el proyecto con la base de datos ya cargada

La base de datos (PostgreSQL) no viaja con el repo de git — te paso el
volcado (`sales_a2_YYYYMMDD.dump`) y el archivo `.env` por separado.
**Ninguno de los dos está ni va a estar en git.**

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

## 5. Crear el entorno virtual e instalar dependencias

```bash
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
