"""
Conocimiento adicional sobre el catálogo de Instigo, usado para dar
recomendaciones por uso (velocidad, distancia, terreno) en vez de solo
buscar por nombre exacto.

IMPORTANTE -- esto es aditivo, no un filtro de qué se puede vender:
- Qué categorías cuentan como "producto vendible" (vs. refacciones,
  gastos, insumos de oficina, etc.) se define en SELLABLE_CATEGORIES,
  copiado directo de las categorías de producto que ya existen en Odoo.
  Si agregan una línea de producto nueva, solo hay que sumarla a esa
  lista -- nada más en el código cambia.
- MODEL_SPECS es solo para que el agente pueda RECOMENDAR mejor cuando el
  cliente no sabe qué modelo quiere. Si un producto no está aquí, se
  puede buscar y cotizar normal igual -- simplemente el agente no tendrá
  specs detalladas para recomendarlo por caso de uso hasta que se
  agreguen. No bloquea nada.

Fuente: https://instigo.mx (revisado julio 2026) y las categorías de
producto configuradas en Odoo. Agrega o actualiza modelos aquí cuando
cambie el catálogo del sitio o cuando quieras que el agente sepa
recomendar una línea nueva (bicicletas, bicimotos, etc).
"""

# Categorías de producto de Odoo que sí son productos vendibles (no
# refacciones, no gastos, no insumos de oficina, no servicios). Tal cual
# como aparecen en Inventario > Configuración > Categorías de producto.
# Para agregar una línea nueva (ej. otra categoría de vehículo), solo
# agrega el nombre exacto aquí.
SELLABLE_CATEGORIES = [
    "Bicicletas Electricas",
    "Bicimoto",
    "Bicimoto electrica",
    "Scooter Electricos",
]

MODEL_SPECS = {
    "URBANO 2.0": {
        "linea": "scooter",
        "velocidad_kmh": 25,
        "autonomia_km": "15-20",
        "terreno": "pavimento liso, ciudad",
        "uso_ideal": "trayectos cortos en la ciudad, primer scooter, presupuesto ajustado",
        "url": "https://instigo.mx/products/urbano-2-0",
    },
    "CITY": {
        "linea": "scooter",
        "velocidad_kmh": 25,
        "autonomia_km": 30,
        "terreno": "pavimento liso, ciudad",
        "uso_ideal": "muy ligero y portátil (14 kg), ideal para combinar con transporte público",
        "url": "https://instigo.mx/products/city",
    },
    "CITY GO": {
        "linea": "scooter",
        "velocidad_kmh": 45,
        "autonomia_km": "45-50",
        "terreno": "pavimento urbano, con suspensión delantera y trasera",
        "uso_ideal": "trayectos urbanos más largos y cómodos, asiento tipo scooter clásico",
        "url": "https://instigo.mx/products/city-go",
    },
    "SPORT 2.0": {
        "linea": "scooter",
        "velocidad_kmh": 45,
        "autonomia_km": 40,
        "terreno": "pavimento y terracería ligera",
        "uso_ideal": "buen balance precio/desempeño para trayectos medios del día a día",
        "url": "https://instigo.mx/products/sport-2-0",
    },
    "SPORT 2.0 PRO": {
        "linea": "scooter",
        "velocidad_kmh": 50,
        "autonomia_km": 40,
        "terreno": "pavimento y terracería ligera",
        "uso_ideal": "como el Sport 2.0 pero con más potencia y respuesta para rutas más exigentes",
        "url": "https://instigo.mx/products/sport-2-0-pro",
    },
    "RUSH": {
        "linea": "scooter",
        "velocidad_kmh": 40,
        "autonomia_km": None,
        "terreno": "todo terreno (llantas 10\" off-road)",
        "uso_ideal": "combina ciudad y aventura, caminos irregulares, sin buscar velocidad extrema",
        "url": "https://instigo.mx/products/instigo-rush",
    },
    "MONSTER 2.0": {
        "linea": "scooter",
        "velocidad_kmh": 70,
        "autonomia_km": 60,
        "terreno": "todo terreno, doble motor",
        "uso_ideal": "distancias largas y terreno irregular, usuarios con algo de experiencia",
        "url": "https://instigo.mx/products/monster-2-0",
    },
    "NIRAN": {
        "linea": "scooter",
        "velocidad_kmh": 70,
        "autonomia_km": 65,
        "terreno": "todo terreno, doble motor",
        "uso_ideal": "trayectos largos priorizando la máxima autonomía y potencia",
        "url": "https://instigo.mx/products/niran",
    },
    "EXTREME": {
        "linea": "scooter",
        "velocidad_kmh": 80,
        "autonomia_km": 60,
        "terreno": "todo terreno, doble motor, frenos hidráulicos",
        "uso_ideal": "usuarios experimentados que buscan la máxima velocidad y potencia",
        "url": "https://instigo.mx/products/extreme",
    },
    "VOLTIA": {
        "linea": "scooter",
        "velocidad_kmh": 45,
        "autonomia_km": 50,
        "terreno": "ciudad, ruedas anchas de 14\" (más estable, estilo motobici)",
        "uso_ideal": "quien busca algo más estable tipo moto/bici que un scooter de pie",
        "url": "https://instigo.mx/products/voltia",
    },
    # TODO: agregar modelos de bicicletas eléctricas y bicimotos aquí
    # cuando se definan -- no requiere ningún otro cambio de código.
}


def normalize_name(name: str) -> str:
    return " ".join(name.split()).strip().upper()


_MODEL_SPECS_NORMALIZED = {normalize_name(k): v for k, v in MODEL_SPECS.items()}


def find_spec(product_name: str):
    """Regresa las specs curadas para un producto de Odoo si su nombre
    contiene alguno de los modelos conocidos (ej. "Scooter electrico
    Monster 2.0" contiene "MONSTER 2.0"). Regresa None si no lo tenemos
    catalogado -- eso NO significa que no se pueda vender, solo que no
    hay specs para recomendarlo por caso de uso."""
    norm = normalize_name(product_name)
    for model_name, spec in _MODEL_SPECS_NORMALIZED.items():
        if model_name in norm:
            return spec
    return None


def format_catalog_for_prompt() -> str:
    lines = []
    for name, spec in MODEL_SPECS.items():
        autonomia = spec["autonomia_km"]
        autonomia_txt = f"{autonomia} km" if autonomia else "N/D"
        lines.append(
            f"- {name}: hasta {spec['velocidad_kmh']} km/h, autonomía {autonomia_txt}, "
            f"terreno: {spec['terreno']}. Ideal para: {spec['uso_ideal']}. "
            f"Link de compra: {spec.get('url', 'N/D')}"
        )
    return "\n".join(lines)
