"""
Cliente delgado para hablar con Odoo (External API vía XML-RPC).
Pensado para correr contra una base de pruebas (duplicado neutralizado
de tu Odoo Custom), no contra producción.

Variables de entorno esperadas (ver .env.example):
  ODOO_URL       -> https://tu-base-pruebas.odoo.com
  ODOO_DB        -> tu-base-pruebas
  ODOO_USERNAME  -> correo del usuario API
  ODOO_API_KEY   -> API key generada en Ajustes > Seguridad de la cuenta
"""

import os
import xmlrpc.client

from catalog import SELLABLE_CATEGORIES


class OdooClient:
    def __init__(self):
        self.url = os.environ["ODOO_URL"].rstrip("/")
        self.db = os.environ["ODOO_DB"]
        self.username = os.environ["ODOO_USERNAME"]
        self.password = os.environ["ODOO_API_KEY"]
        self._uid = None
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def uid(self):
        if self._uid is None:
            self._uid = self._common.authenticate(self.db, self.username, self.password, {})
            if not self._uid:
                raise RuntimeError("No se pudo autenticar contra Odoo. Revisa ODOO_* en .env")
        return self._uid

    def call(self, model, method, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or {}
        return self._models.execute_kw(
            self.db, self.uid(), self.password, model, method, args, kwargs
        )

    # --- Catálogo -----------------------------------------------------

    def search_products(self, query, limit=5):
        # OJO: usamos product.product (variante), no product.template.
        # sale.order.line.product_id espera un ID de product.product; si
        # buscáramos en product.template el ID no coincide y create_quotation
        # falla en silencio (Odoo no encuentra el producto).
        #
        # Filtramos por categ_id.name contra la lista de categorías
        # vendibles (ver catalog.SELLABLE_CATEGORIES) -- así refacciones,
        # gastos, insumos de oficina, etc. quedan fuera de raíz aunque
        # compartan palabras del nombre con un producto real. Agregar una
        # categoría nueva es solo sumarla a esa lista, nada más.
        domain = [["name", "ilike", query]] + self._sellable_category_domain()
        fields = ["id", "name", "list_price", "qty_available", "default_code"]
        results = self.call(
            "product.product", "search_read", [domain], {"fields": fields, "limit": limit}
        )
        return results

    @staticmethod
    def _sellable_category_domain():
        """Domain estilo Odoo (notación polaca) para "categ_id.name es
        cualquiera de SELLABLE_CATEGORIES", sin importar cuántas haya."""
        terms = [["categ_id.name", "ilike", name] for name in SELLABLE_CATEGORIES]
        if not terms:
            return []
        return (["|"] * (len(terms) - 1)) + terms

    # --- Helpdesk (Refacciones/Garantía y Facturación) -----------------

    def create_helpdesk_ticket(self, team_name, name, description, partner_name, partner_phone):
        team_ids = self.call("helpdesk.team", "search", [[["name", "=", team_name]]])
        vals = {
            "name": name,
            "description": description,
            "partner_name": partner_name,
            "partner_phone": partner_phone,
        }
        if team_ids:
            vals["team_id"] = team_ids[0]
        return self.call("helpdesk.ticket", "create", [vals])

    # --- CRM (Información de producto) ---------------------------------

    def create_crm_opportunity(self, name, contact_name, phone, description,
                                source_name="WhatsApp bot (MVP)"):
        source_ids = self.call("utm.source", "search", [[["name", "=", source_name]]])
        vals = {
            "name": name,
            "contact_name": contact_name,
            "phone": phone,
            "description": description,
            "type": "opportunity",
        }
        if source_ids:
            vals["source_id"] = source_ids[0]
        return self.call("crm.lead", "create", [vals])

    def append_to_opportunity_notes(self, opportunity_id, extra_text):
        """Agrega texto al final de la descripción de una oportunidad ya
        creada (por ejemplo, la referencia de la cotización generada)."""
        current = self.call("crm.lead", "read", [[opportunity_id]], {"fields": ["description"]})
        description = (current[0].get("description") or "") if current else ""
        self.call(
            "crm.lead", "write", [[opportunity_id], {"description": f"{description}\n\n{extra_text}"}]
        )

    # --- Cotización ------------------------------------------------------

    def create_quotation(self, partner_name, phone, product_id, qty, opportunity_id=None):
        partner_ids = self.call("res.partner", "search", [[["name", "=", partner_name]]])
        partner_id = (
            partner_ids[0]
            if partner_ids
            else self.call("res.partner", "create", [{"name": partner_name, "phone": phone}])
        )
        # La API directa NO dispara los onchange que en la UI rellenan
        # 'name' y 'price_unit' de la línea a partir del producto, así que
        # los mandamos explícitos para no dejar la línea incompleta.
        product = self.call(
            "product.product", "read", [[product_id]], {"fields": ["name", "list_price"]}
        )[0]
        order_vals = {
            "partner_id": partner_id,
            "order_line": [
                (
                    0,
                    0,
                    {
                        "product_id": product_id,
                        "name": product["name"],
                        "product_uom_qty": qty,
                        "price_unit": product["list_price"],
                    },
                )
            ],
        }
        if opportunity_id:
            order_vals["opportunity_id"] = opportunity_id
        order_id = self.call("sale.order", "create", [order_vals])
        if opportunity_id:
            self.append_to_opportunity_notes(
                opportunity_id, f"Cotización generada: pedido de venta #{order_id}"
            )
        return order_id

    def resolve_xmlid(self, module, name):
        """Resuelve un external ID (ej. 'sale', 'email_template_edi_sale')
        a un res_id, vía el método público estándar para esto en RPC."""
        _model, res_id = self.call("ir.model.data", "check_object_reference", [module, name])
        return res_id

    def send_quotation_email(self, order_id, email):
        """Manda la cotización por correo usando la plantilla y la acción
        estándar de Odoo (la misma que dispara el botón "Enviar por correo"
        de una cotización) -- así el PDF que recibe el cliente es el
        reporte oficial de Odoo, ya con adjunto y todo."""
        order = self.call("sale.order", "read", [[order_id]], {"fields": ["partner_id"]})[0]
        partner_id = order["partner_id"][0]
        partner = self.call("res.partner", "read", [[partner_id]], {"fields": ["email"]})[0]
        if not partner.get("email"):
            self.call("res.partner", "write", [[partner_id], {"email": email}])

        template_id = self.resolve_xmlid("sale", "email_template_edi_sale")
        self.call(
            "mail.template",
            "send_mail",
            [template_id, order_id],
            {"force_send": True, "email_values": {"email_to": email}},
        )

    # --- Adjuntos (video del cliente) -------------------------------------

    def create_attachment(self, res_model, res_id, filename, base64_data):
        vals = {
            "name": filename,
            "res_model": res_model,
            "res_id": res_id,
            "datas": base64_data,
        }
        return self.call("ir.attachment", "create", [vals])

    def update_attachment(self, attachment_id, base64_data):
        self.call("ir.attachment", "write", [[attachment_id], {"datas": base64_data}])


odoo = OdooClient()
