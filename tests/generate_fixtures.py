"""Generate realistic test fixture data for MCP dashboard testing.

Creates 3 files with ~10k rows each:
  - sales_transactions.csv  (sales data from multiple branches)
  - inventory_levels.xlsx   (inventory tracking across warehouses)
  - customer_orders.xlsx    (customer order history)

All data is fictional but coherent: dates, amounts, categories, etc.
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

OUT = Path(__file__).parent / "fixtures"
OUT.mkdir(exist_ok=True)

# --- Shared reference data ---

BRANCHES = [
    "Norte", "Sur", "Centro", "Este", "Oeste",
    "Poniente", "Levante", "Medio Oriente",
]
PRODUCT_CATEGORIES = [
    "Abarrotes", "Lacteos", "Bebidas", "Limpieza",
    "Snacks", "Carnes", "Panaderia", "Frutas",
    "Verduras", "Congelados",
]
PRODUCTS = {
    "Abarrotes": ["Arroz 5kg", "Frijoles 1kg", "Aceite 1L", "Azucar 1kg", "Sal 500g", "Pasta 500g"],
    "Lacteos": ["Leche 1L", "Queso 500g", "Yogurt 200g", "Mantequilla 250g", "Crema 500ml"],
    "Bebidas": ["Agua 1L", "Refresco 600ml", "Jugo 1L", "Cerveza 355ml", "Cafe 200g"],
    "Limpieza": ["Detergente 1L", "Cloro 1L", "Jabon 250g", "Desinfectante 500ml"],
    "Snacks": ["Papas 150g", "Galletas 200g", "Chocolate 100g", "Nueces 250g"],
    "Carnes": ["Pollo 1kg", "Res 500g", "Cerdo 500g", "Jamón 300g"],
    "Panaderia": ["Pan blanco", "Pan integral", "Bolillo x10", "Concha x6"],
    "Frutas": ["Manzana 1kg", "Platano 1kg", "Naranja 1kg", "Fresa 500g"],
    "Verduras": ["Tomate 1kg", "Cebolla 1kg", "Lechuga", "Zanahoria 500g"],
    "Congelados": ["Pizza", "Helado 1L", "Papas fritas 400g", "Nuggets 500g"],
}
PAYMENT_METHODS = ["Efectivo", "Tarjeta Debito", "Tarjeta Credito", "Transferencia", "NFC"]
SHIFTS = ["Matutino", "Vespertino", "Nocturno"]
CASHIERS = [f"Cajero-{i:02d}" for i in range(1, 21)]
WAREHOUSES = ["Almacen Central", "Almacen Norte", "Almacen Sur", "Almacen Este"]
CUSTOMER_TYPES = ["Minorista", "Mayorista", "Premium", "Regular"]
STATUSES = ["Completado", "En Proceso", "Cancelado", "Devuelto"]

start_date = datetime(2024, 1, 1)
end_date = datetime(2025, 12, 31)
date_range_days = (end_date - start_date).days


def random_date() -> datetime:
    return start_date + timedelta(days=random.randint(0, date_range_days))


# --- 1. Sales Transactions CSV (~10k rows) ---

def generate_sales(n: int = 10_000) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        branch = random.choice(BRANCHES)
        category = random.choice(PRODUCT_CATEGORIES)
        product = random.choice(PRODUCTS[category])
        qty = random.randint(1, 15)
        unit_price = round(random.uniform(5.0, 500.0), 2)
        total = round(qty * unit_price, 2)
        discount = round(random.uniform(0, 0.15), 2) if random.random() < 0.3 else 0.0
        net = round(total * (1 - discount), 2)
        rows.append({
            "Transaction_ID": f"TXN-{random.randint(100000, 999999)}",
            "Branch": branch,
            "Date": random_date().strftime("%Y-%m-%d"),
            "Product": product,
            "Product_Category": category,
            "Quantity": qty,
            "Unit_Price": unit_price,
            "Total": total,
            "Discount": discount,
            "Net_Amount": net,
            "Payment_Method": random.choice(PAYMENT_METHODS),
            "Shift": random.choice(SHIFTS),
            "Cashier": random.choice(CASHIERS),
        })
    return pd.DataFrame(rows)


# --- 2. Inventory Levels XLSX (~10k rows) ---

def generate_inventory(n: int = 10_000) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        category = random.choice(PRODUCT_CATEGORIES)
        product = random.choice(PRODUCTS[category])
        warehouse = random.choice(WAREHOUSES)
        qty = random.randint(0, 500)
        reorder_point = random.randint(20, 100)
        unit_cost = round(random.uniform(2.0, 300.0), 2)
        status = "OK" if qty > reorder_point else ("Low" if qty > 0 else "Out of Stock")
        rows.append({
            "Inventory_ID": f"INV-{random.randint(100000, 999999)}",
            "Product": product,
            "Product_Category": category,
            "Warehouse": warehouse,
            "Quantity_On_Hand": qty,
            "Reorder_Point": reorder_point,
            "Unit_Cost": unit_cost,
            "Total_Value": round(qty * unit_cost, 2),
            "Status": status,
            "Last_Updated": random_date().strftime("%Y-%m-%d"),
        })
    return pd.DataFrame(rows)


# --- 3. Customer Orders XLSX (~10k rows) ---

def generate_customer_orders(n: int = 10_000) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        customer_type = random.choice(CUSTOMER_TYPES)
        category = random.choice(PRODUCT_CATEGORIES)
        product = random.choice(PRODUCTS[category])
        qty = random.randint(1, 50)
        unit_price = round(random.uniform(5.0, 500.0), 2)
        total = round(qty * unit_price, 2)
        status = random.choices(STATUSES, weights=[70, 15, 10, 5])[0]
        rows.append({
            "Order_ID": f"ORD-{random.randint(100000, 999999)}",
            "Customer_Name": f"Cliente-{random.randint(1, 500):04d}",
            "Customer_Type": customer_type,
            "Branch": random.choice(BRANCHES),
            "Order_Date": random_date().strftime("%Y-%m-%d"),
            "Product": product,
            "Product_Category": category,
            "Quantity": qty,
            "Unit_Price": unit_price,
            "Total": total,
            "Payment_Method": random.choice(PAYMENT_METHODS),
            "Status": status,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print("Generating sales_transactions.csv ...")
    sales = generate_sales(10_000)
    csv_path = OUT / "sales_transactions.csv"
    sales.to_csv(csv_path, index=False)
    print(f"  {csv_path.name}: {len(sales):,} rows, {csv_path.stat().st_size / 1024:.0f} KB")

    print("Generating inventory_levels.xlsx ...")
    inventory = generate_inventory(10_000)
    xlsx_path1 = OUT / "inventory_levels.xlsx"
    inventory.to_excel(xlsx_path1, index=False, engine="openpyxl")
    print(f"  {xlsx_path1.name}: {len(inventory):,} rows, {xlsx_path1.stat().st_size / 1024:.0f} KB")

    print("Generating customer_orders.xlsx ...")
    orders = generate_customer_orders(10_000)
    xlsx_path2 = OUT / "customer_orders.xlsx"
    orders.to_excel(xlsx_path2, index=False, engine="openpyxl")
    print(f"  {xlsx_path2.name}: {len(orders):,} rows, {xlsx_path2.stat().st_size / 1024:.0f} KB")

    print("Done!")
