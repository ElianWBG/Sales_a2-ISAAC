
#   SENTENCIAS DEL ORM DE DJANGO — con descripción de cada una          
#   Proyecto Sales_A2 · billing                                          
#   Cada bloque: DESCRIPCIÓN + sentencia + SQL generado + resultado      




#  CREATE  (crear / insertar registros)


# ── [1] Crear una marca con nombre y descripción ────────────────────────
# QUÉ HACE: .create() instancia el objeto y lo guarda en la BD en UN solo
#           paso (equivale a Brand(...) + .save()). Genera un INSERT.
#  In [1]: samsung = Brand.objects.create(name='Samsung', description='Electronics')
# INSERT INTO "billing_brand" ("name", "description", "is_active", "created_at", "updated_at")
# VALUES ('Samsung', 'Electronics', 1, '2026-06-22 01:51:44.725399', '2026-06-22 01:51:44.725428') RETURNING "billing_brand"."id"
# Execution time: 0.000297s [Database: default]

# ── [2] Crear una marca SOLO con nombre ─────────────────────────────────
# QUÉ HACE: igual que arriba, pero como no se pasa description, ese campo
#           se guarda como NULL (porque el modelo permite blank/null).
# In [2]: apple = Brand.objects.create(name='Apple')
# INSERT INTO "billing_brand" ("name", "description", "is_active", "created_at", "updated_at")
# VALUES ('Apple', NULL, 1, '2026-06-22 01:50:24.482443', '2026-06-22 01:50:24.482490') RETURNING "billing_brand"."id"
# Execution time: 0.001708s [Database: default]

# ── [3] Crear un grupo / categoría de productos ─────────────────────────
# QUÉ HACE: inserta un ProductGroup llamado 'Electronics'.
# In [3]: electronics = ProductGroup.objects.create(name='Electronics')
# INSERT INTO "billing_productgroup" ("name", "is_active", "created_at", "updated_at")
# VALUES ('Electronics', 1, '2026-06-22 01:53:05.912144', '2026-06-22 01:53:05.912163') RETURNING "billing_productgroup"."id"
# Execution time: 0.002287s [Database: default]

# ── [4] Crear un proveedor con email ────────────────────────────────────
# QUÉ HACE: inserta un Supplier; los campos no enviados (contact_name,
#           phone, address) quedan NULL.
# In [4]: dist = Supplier.objects.create(name='TechDist', email='info@tech.com')
# INSERT INTO "billing_supplier" ("name", "contact_name", "email", "phone", "address", "is_active", "created_at", "updated_at")
# VALUES ('TechDist', NULL, 'info@tech.com', NULL, NULL, 1, '2026-06-22 01:53:35.182849', '2026-06-22 01:53:35.182870') RETURNING "billing_supplier"."id"
# Execution time: 0.002105s [Database: default]

# ── [5] Crear un proveedor solo con nombre ──────────────────────────────
# QUÉ HACE: inserta otro Supplier; todo lo demás queda NULL.
# In [5]: global_s = Supplier.objects.create(name='GlobalSupply')
# INSERT INTO "billing_supplier" ("name", "contact_name", "email", "phone", "address", "is_active", "created_at", "updated_at")
# VALUES ('GlobalSupply', NULL, NULL, NULL, NULL, 1, '2026-06-22 01:54:29.145354', '2026-06-22 01:54:29.145369') RETURNING "billing_supplier"."id"
# Execution time: 0.001747s [Database: default]

# ── [6] Crear un producto enlazado a marca y grupo (ForeignKey) ─────────
# QUÉ HACE: inserta un Product. brand=samsung y group=electronics son
#           ForeignKeys: en la BD se guardan como brand_id y group_id.
# In [6]: phone = Product.objects.create(name='Galaxy S24', brand=samsung, group=electronics, unit_price=999.99, stock=50)
# INSERT INTO "billing_product" ("name", "description", "brand_id", "group_id", "unit_price", "stock", "image", "is_active", "created_at", "updated_at")
# VALUES ('Galaxy S24', NULL, 10, 5, '999.990000000', 50, '', 1, '2026-06-22 02:13:54.728641', '2026-06-22 02:13:54.728673') RETURNING "billing_product"."id"
# Execution time: 0.002147s [Database: default]

# ── [7] Asociar proveedores a un producto (ManyToMany .add) ─────────────
# QUÉ HACE: agrega 2 proveedores al producto. Como es M2M, no toca la
#           tabla product; inserta filas en la tabla intermedia
#           billing_product_suppliers (product_id, supplier_id).
# In [7]: phone.suppliers.add(dist, global_s)
# BEGIN
# Execution time: 0.000034s [Database: default]
# INSERT OR IGNORE INTO "billing_product_suppliers" ("product_id", "supplier_id")
# VALUES (5, 6), (5, 7)
# Execution time: 0.001592s [Database: default]

# ── [8] Crear un cliente ────────────────────────────────────────────────
# QUÉ HACE: inserta un Customer con dni, nombre y apellido.
# In [8]: client = Customer.objects.create(dni='0912345678', first_name='Juan', last_name='Perez')
# INSERT INTO "billing_customer" ("dni", "first_name", "last_name", "email", "phone", "address", "is_active", "created_at", "updated_at")
# VALUES ('0912345678', 'Juan', 'Perez', NULL, NULL, NULL, 1, '2026-06-22 02:14:52.865441', '2026-06-22 02:14:52.865463') RETURNING "billing_customer"."id"
# Execution time: 0.001027s [Database: default]

# ── [9] Crear el perfil 1:1 de un cliente (OneToOne) ────────────────────
# QUÉ HACE: inserta el CustomerProfile ligado al cliente. customer=client
#           es OneToOne: un cliente solo puede tener un perfil.
# In [9]: profile = CustomerProfile.objects.create(customer=client, taxpayer_type='ruc', payment_terms='credit_30', credit_limit=5000)
# INSERT INTO "billing_customerprofile" ("customer_id", "taxpayer_type", "payment_terms", "credit_limit", "notes")
# VALUES (5, 'ruc', 'credit_30', '5000', NULL) RETURNING "billing_customerprofile"."id"
# Execution time: 0.001815s [Database: default]

# ── [10] Crear la cabecera de una factura ───────────────────────────────
# QUÉ HACE: inserta un Invoice ligado al cliente, con subtotal, IVA y total.
# In [10]: inv = Invoice.objects.create(customer=client, subtotal=999.99, tax=120, total=1119.99)
# INSERT INTO "billing_invoice" ("customer_id", "invoice_date", "subtotal", "tax", "total", "is_active")
# VALUES (5, '2026-06-22 02:21:31.660917', '999.990000000', '120', '1119.99000000', 1) RETURNING "billing_invoice"."id"
# Execution time: 0.002084s [Database: default]

# ── [11] Crear una línea de detalle de la factura ───────────────────────
# QUÉ HACE: inserta un InvoiceDetail (producto + cantidad + precio) ligado
#           a la factura inv. Es la relación padre-hijo (Invoice→Detail).
# In [11]: det = InvoiceDetail.objects.create(invoice=inv, product=phone, quantity=1, unit_price=phone.unit_price)
# INSERT INTO "billing_invoicedetail" ("invoice_id", "product_id", "quantity", "unit_price", "subtotal")
# VALUES (10, 5, 1, '999.990000000', '999.990000000') RETURNING "billing_invoicedetail"."id"
# Execution time: 0.001035s [Database: default]

# ── [11b] Crear una marca y ver el objeto devuelto ──────────────────────
# QUÉ HACE: crea la marca 'Nike'. El Out[11] <Brand: Nike> es lo que
#           devuelve .create(): el objeto recién creado (usa su __str__).
# In [11]: Brand.objects.create(name='Nike')
# INSERT INTO "billing_brand" ("name", "description", "is_active", "created_at", "updated_at")
# VALUES ('Nike', NULL, 1, '2026-06-22 02:46:53.581238', '2026-06-22 02:46:53.581263') RETURNING "billing_brand"."id"
# Execution time: 0.001484s [Database: default]
# Out[11]: <Brand: Nike>


# ════════════════════════════════════════════════════════════════════════
#  READ  (leer / consultar registros)
# ════════════════════════════════════════════════════════════════════════

# ── [26] Traer TODOS los registros ──────────────────────────────────────
# QUÉ HACE: .all() devuelve un QuerySet con todas las marcas. El ORDER BY
#           name sale del Meta.ordering del modelo. El LIMIT 21 lo agrega
#           el shell para previsualizar (no es tuyo).
# In [26]: Brand.objects.all()
# Out[26]: SELECT ... FROM "billing_brand" ORDER BY "billing_brand"."name" ASC LIMIT 21
# Execution time: 0.000297s [Database: default]
# <QuerySet [<Brand: Apple>, <Brand: Samsung>]>

# ── [27] Traer UN registro exacto (.get) ────────────────────────────────
# QUÉ HACE: .get() devuelve un único objeto que cumpla la condición.
#           OJO: lanza error si no existe (DoesNotExist) o si hay más de
#           uno (MultipleObjectsReturned).
# In [27]: Brand.objects.get(name='Samsung')
# SELECT ... FROM "billing_brand" WHERE "billing_brand"."name" = 'Samsung' LIMIT 21
# Execution time: 0.000176s [Database: default]
# Out[27]: <Brand: Samsung>

# ── [28] Filtrar con "mayor que" (__gt) ─────────────────────────────────
# QUÉ HACE: trae productos con precio MAYOR a 500. El lookup __gt =
#           "greater than" → en SQL se traduce a > 500.
# In [28]: Product.objects.filter(unit_price__gt=500)
# WHERE "billing_product"."unit_price" > '500'
# Execution time: 0.000287s [Database: default]
# <QuerySet [<Product: Galaxy S24 (Samsung)>]>

# ── [29] Filtrar por rango (__range) ────────────────────────────────────
# QUÉ HACE: trae productos con precio ENTRE 100 y 500 (incluidos). El
#           lookup __range se traduce a BETWEEN. Resultado vacío porque
#           el único producto cuesta 999.99.
# In [29]: Product.objects.filter(unit_price__range=(100,500))
# WHERE "billing_product"."unit_price" BETWEEN '100' AND '500'
# Execution time: 0.000295s [Database: default]
# <QuerySet []>

# ── [30] Buscar texto sin importar mayúsculas (__icontains) ─────────────
# QUÉ HACE: trae productos cuyo nombre CONTENGA 'gal' (la i = insensible
#           a mayúsculas). Se traduce a LIKE '%gal%'. Es el filtro típico
#           de las barras de búsqueda.
# In [30]: Product.objects.filter(name__icontains='gal')
# WHERE "billing_product"."name" LIKE '%gal%' ESCAPE '\'
# Execution time: 0.000446s [Database: default]
# <QuerySet [<Product: Galaxy S24 (Samsung)>]>

# ── [31] Excluir registros (.exclude) ───────────────────────────────────
# QUÉ HACE: trae TODOS los productos MENOS los que tengan stock = 0.
#           Es lo contrario de filter (genera un NOT en el WHERE).
# In [31]: Product.objects.exclude(stock=0)
# WHERE NOT ("billing_product"."stock" = 0)
# Execution time: 0.000227s [Database: default]
# <QuerySet [<Product: Galaxy S24 (Samsung)>]>

# ── [32] Ordenar resultados (.order_by) ─────────────────────────────────
# QUÉ HACE: ordena los productos por precio. El guion '-' indica DESC
#           (de mayor a menor). Sin guion sería ascendente.
# In [32]: Product.objects.order_by('-unit_price')
# ORDER BY "billing_product"."unit_price" DESC
# Execution time: 0.000326s [Database: default]
# <QuerySet [<Product: Galaxy S24 (Samsung)>]>

# ── [33] Contar registros (.count) ──────────────────────────────────────
# QUÉ HACE: devuelve cuántos productos hay. Genera COUNT(*); es más
#           eficiente que len(...) porque cuenta en la BD, no en Python.
# In [33]: Product.objects.count()
# SELECT COUNT(*) AS "__count" FROM "billing_product"
# Execution time: 0.000193s [Database: default]
# Out[33]: 1

# ── [34] Verificar si existe algo (.exists) ─────────────────────────────
# QUÉ HACE: devuelve True/False según si hay al menos un producto con
#           stock 0. Es lo más eficiente para preguntar "¿existe?" porque
#           usa LIMIT 1.
# In [34]: Product.objects.filter(stock=0).exists()
# SELECT 1 AS "a" FROM "billing_product" WHERE "billing_product"."stock" = 0 LIMIT 1
# Execution time: 0.000226s [Database: default]
# Out[34]: False


# ════════════════════════════════════════════════════════════════════════
#  UPDATE  (modificar registros)
# ════════════════════════════════════════════════════════════════════════

# ── [35] Modificar un objeto y guardarlo (.save) ────────────────────────
# QUÉ HACE: patrón "traer → modificar en Python → guardar". El .get()
#           hace un SELECT, y .save() hace un UPDATE de TODA la fila.
# In [35]: b = Brand.objects.get(name='Samsung'); b.description = 'Updated'; b.save()
# UPDATE "billing_brand" SET "name"='Samsung', "description"='Updated', ... WHERE "billing_brand"."id" = 10
# Execution time: 0.003914s [Database: default]

# ── [36] Traer un producto para luego modificar sus relaciones ──────────
# QUÉ HACE: SELECT del producto Galaxy S24 y lo guarda en la variable p.
# In [36]: p = Product.objects.get(name='Galaxy S24')
# SELECT ... FROM "billing_product" WHERE "billing_product"."name" = 'Galaxy S24' LIMIT 21
# Execution time: 0.000187s [Database: default]

# ── [37] Agregar un elemento a una relación M2M (.add) ──────────────────
# QUÉ HACE: añade el proveedor global_s al producto. Inserta una fila en
#           la tabla intermedia. El "OR IGNORE" evita duplicar si ya existe.
# In [37]: p.suppliers.add(global_s)
# INSERT OR IGNORE INTO "billing_product_suppliers" ("product_id", "supplier_id") VALUES (5, 7)
# Execution time: 0.000885s [Database: default]

# ── [38] Quitar un elemento de una relación M2M (.remove) ───────────────
# QUÉ HACE: desvincula ese proveedor del producto. Borra SOLO la fila de
#           la tabla intermedia; el proveedor sigue existiendo.
# In [38]: p.suppliers.remove(global_s)
# DELETE FROM "billing_product_suppliers" WHERE (product_id = 5 AND supplier_id IN (7))
# Execution time: 0.001146s [Database: default]

# ── [39] Vaciar TODA una relación M2M (.clear) ──────────────────────────
# QUÉ HACE: quita TODOS los proveedores del producto de una sola vez
#           (sin tocar la tabla de proveedores).
# In [39]: p.suppliers.clear()
# DELETE FROM "billing_product_suppliers" WHERE "product_id" = 5
# Execution time: 0.001305s [Database: default]

# ── [40] Reemplazar el contenido de una M2M (.set) ──────────────────────
# QUÉ HACE: deja la relación EXACTAMENTE con la lista dada. Django compara
#           lo que hay con lo que pides: borra lo que sobra y agrega lo que
#           falta (acá termina solo con 'dist').
# In [40]: p.suppliers.set([dist])
# INSERT OR IGNORE INTO "billing_product_suppliers" ("product_id", "supplier_id") VALUES (5, 6)
# Execution time: 0.001167s [Database: default]

# ── [41] Traer un cliente por su DNI ────────────────────────────────────
# QUÉ HACE: SELECT del cliente con ese dni para modificar luego su perfil.
# In [41]: c = Customer.objects.get(dni='0912345678')
# SELECT ... FROM "billing_customer" WHERE "billing_customer"."dni" = '0912345678' LIMIT 21
# Execution time: 0.000200s [Database: default]

# ── [42] Modificar un objeto relacionado 1:1 y guardarlo ────────────────
# QUÉ HACE: accede al perfil del cliente (OneToOne), le cambia el cupo y
#           guarda. El primer SELECT trae el perfil; luego UPDATE.
# In [42]: c.profile.credit_limit = 10000; c.profile.save()
# UPDATE "billing_customerprofile" SET "credit_limit"='10000', ... WHERE "id" = 3
# Execution time: 0.003536s [Database: default]

# ── [44] Actualización MASIVA con F() ───────────────────────────────────
# QUÉ HACE: sube el precio 10% a TODOS los productos en UNA query, sin
#           traerlos a Python. F('unit_price') referencia el valor actual
#           de la columna en la BD (evita condiciones de carrera). El Out
#           = 1 es el número de filas afectadas.
# In [44]: Product.objects.update(unit_price=F('unit_price') * 1.10)
# UPDATE "billing_product" SET "unit_price" = ("billing_product"."unit_price" * 1.1)
# Execution time: 0.005159s [Database: default]
# Out[44]: 1


# ════════════════════════════════════════════════════════════════════════
#  DELETE  (eliminar registros)
# ════════════════════════════════════════════════════════════════════════

# ── [47] Traer y eliminar un objeto (.delete) ───────────────────────────
# QUÉ HACE: borra la marca Nike. Antes del DELETE, Django hace un SELECT
#           de productos hijos para respetar el on_delete. El Out
#           (1, {'billing.Brand': 1}) = total borrado y desglose por modelo.
# In [47]: Brand.objects.get(name='Nike').delete()
# DELETE FROM "billing_brand" WHERE "billing_brand"."id" IN (12)
# Execution time: 0.001024s [Database: default]
# Out[47]: (1, {'billing.Brand': 1})

# ── [48] Eliminación por filtro (borrado masivo) ────────────────────────
# QUÉ HACE: intenta borrar marcas llamadas 'Nike'. Como ya no existe (la
#           borramos arriba), no elimina nada → Out (0, {}).
# In [48]: Brand.objects.filter(name='Nike').delete()
# Execution time: 0.000182s [Database: default]
# Out[48]: (0, {})

# ── [50] Quitar un proveedor de la M2M de un producto ───────────────────
# QUÉ HACE: desvincula 'dist' del producto (borra la fila intermedia).
# In [50]: phone.suppliers.remove(dist)
# DELETE FROM "billing_product_suppliers" WHERE (product_id = 5 AND supplier_id IN (6))
# Execution time: 0.001202s [Database: default]


# ════════════════════════════════════════════════════════════════════════
#  RELACIONES  (navegar entre tablas por FK / M2M / OneToOne)
# ════════════════════════════════════════════════════════════════════════

# ── [52] Acceder a la marca de un producto (FK hacia adelante) ──────────
# QUÉ HACE: desde el producto saltas a su marca por la ForeignKey y lees
#           su nombre. No requiere SQL nuevo si ya estaba cargada.
# In [52]: phone.brand.name
# Out[52]: 'Samsung'

# ── [53] Relación inversa de una FK (related_name) ──────────────────────
# QUÉ HACE: desde la marca obtienes TODOS sus productos. samsung.products
#           funciona gracias al related_name='products' en el FK del modelo.
# In [53]: samsung.products.all()
# WHERE "billing_product"."brand_id" = 10
# Execution time: 0.000580s [Database: default]
# <QuerySet [<Product: Galaxy S24 (Samsung)>]>

# ── [54-55] Proveedores de un producto (M2M con JOIN) ───────────────────
# QUÉ HACE: lista los proveedores del producto. Hace un INNER JOIN con la
#           tabla intermedia. Sale vacío porque ya los quitamos antes.
# In [54]: phone.suppliers.all()
# INNER JOIN "billing_product_suppliers" ... WHERE "product_id" = 5
# Execution time: 0.000274s [Database: default]
# <QuerySet []>

# ── [56] Relación inversa de una M2M ────────────────────────────────────
# QUÉ HACE: desde el proveedor obtienes sus productos (el otro lado de la
#           M2M). Vacío porque ya no hay vínculos.
# In [56]: dist.products.all()
# INNER JOIN ... WHERE "billing_product_suppliers"."supplier_id" = 6
# Execution time: 0.000376s [Database: default]
# <QuerySet []>

# ── [57] Filtrar cruzando una M2M (doble guion __) ──────────────────────
# QUÉ HACE: trae productos cuyo proveedor se llame 'TechDist'. El
#           suppliers__name salta de Product → Supplier por la M2M.
# In [57]: Product.objects.filter(suppliers__name='TechDist')
# INNER JOIN billing_supplier ... WHERE "billing_supplier"."name" = 'TechDist'
# Execution time: 0.000269s [Database: default]
# <QuerySet []>

# ── [58] Acceder al perfil 1:1 de un cliente ────────────────────────────
# QUÉ HACE: desde el cliente lees un dato de su perfil (OneToOne).
# In [58]: client.profile.credit_limit
# Out[58]: 5000

# ── [59] Filtrar cruzando un OneToOne ───────────────────────────────────
# QUÉ HACE: trae clientes cuyo perfil tenga taxpayer_type='ruc'. El
#           profile__taxpayer_type salta de Customer → CustomerProfile.
# In [59]: Customer.objects.filter(profile__taxpayer_type='ruc')
# INNER JOIN billing_customerprofile ... WHERE "taxpayer_type" = 'ruc'
# Execution time: 0.000236s [Database: default]
# <QuerySet [<Customer: Perez, Juan>]>

# ── [60-61] Consulta con OR usando Q() ──────────────────────────────────
# QUÉ HACE: trae productos que sean marca Samsung O cuesten más de 1000.
#           El operador | entre objetos Q genera un OR en el WHERE. (Con &
#           sería AND.) Sirve para condiciones que filter() normal no cubre.
# In [60]: from django.db.models import Q
# In [61]: Product.objects.filter(Q(brand__name='Samsung') | Q(unit_price__gt=1000))
# WHERE ("billing_brand"."name" = 'Samsung' OR "billing_product"."unit_price" > '1000')
# Execution time: 0.000276s [Database: default]
# <QuerySet [<Product: Galaxy S24 (Samsung)>]>


# ════════════════════════════════════════════════════════════════════════
#  AGREGACIONES  (cálculos sobre conjuntos: promedios, sumas, conteos)
# ════════════════════════════════════════════════════════════════════════

# In [62]: from django.db.models import Sum, Avg, Max, Min, Count

# ── [63] Promedio de una columna (.aggregate + Avg) ─────────────────────
# QUÉ HACE: calcula el precio promedio de TODOS los productos. aggregate
#           devuelve un diccionario con un único número (no un QuerySet).
# In [63]: Product.objects.aggregate(avg=Avg('unit_price'))
# SELECT AVG("billing_product"."unit_price") AS "avg" FROM "billing_product"
# Execution time: 0.000301s [Database: default]
# Out[63]: {'avg': Decimal('1099.98900000000')}

# ── [64] Máximo y mínimo a la vez ───────────────────────────────────────
# QUÉ HACE: en una sola consulta obtiene el precio más alto y el más bajo.
#           Como hay un solo producto, max y min son iguales.
# In [64]: Product.objects.aggregate(max=Max('unit_price'), min=Min('unit_price'))
# SELECT MAX(...) AS "max", MIN(...) AS "min" FROM "billing_product"
# Execution time: 0.000301s [Database: default]
# Out[64]: {'max': Decimal('1099.98900000000'), 'min': Decimal('1099.98900000000')}

# ── [65] Suma con filtro (.filter + .aggregate + Sum) ───────────────────
# QUÉ HACE: suma el total de las facturas de un cliente específico. Primero
#           filtra por dni (JOIN con customer), luego suma la columna total.
# In [65]: Invoice.objects.filter(customer__dni='0912345678').aggregate(total=Sum('total'))
# SELECT SUM("billing_invoice"."total") AS "total" ... WHERE "billing_customer"."dni" = '0912345678'
# Execution time: 0.000255s [Database: default]
# Out[65]: {'total': Decimal('1119.99000000000')}

# ── [66] Contar por grupo (.annotate + Count) = GROUP BY ────────────────
# QUÉ HACE: cuenta cuántos productos tiene CADA marca. annotate agrega una
#           columna calculada POR FILA (a diferencia de aggregate que da un
#           solo número). El LEFT JOIN incluye marcas con 0 productos.
#           .values() elige qué columnas mostrar.
# In [66]: Brand.objects.annotate(n=Count('products')).values('name', 'n')
# SELECT "name", COUNT("billing_product"."id") AS "n" ... GROUP BY "billing_brand"."id"
# Execution time: 0.000283s [Database: default]
# <QuerySet [{'name': 'Samsung', 'n': 1}, {'name': 'Apple', 'n': 0}]>

# ── [67] Contar elementos de una M2M por fila ───────────────────────────
# QUÉ HACE: cuenta cuántos proveedores tiene cada producto. Mismo patrón
#           annotate + Count, pero contando sobre la relación M2M.
# In [67]: Product.objects.annotate(ns=Count('suppliers')).values('name', 'ns')
# SELECT "name", COUNT("billing_product_suppliers"."supplier_id") AS "ns" ... GROUP BY "billing_product"."id"
# Execution time: 0.000345s [Database: default]
# <QuerySet [{'name': 'Galaxy S24', 'ns': 0}]>