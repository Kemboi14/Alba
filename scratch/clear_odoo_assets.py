import psycopg2

def clear_assets():
    conn = psycopg2.connect(
        dbname="alba_db",
        user="nick",
        password="nick",
        host="localhost"
    )
    cur = conn.cursor()
    try:
        print("Clearing Odoo assets from database...")
        # Delete attachments related to assets
        cur.execute("DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%'")
        print(f"Deleted {cur.rowcount} asset attachments.")
        
        # Also clear the asset bundles from ir_asset if applicable (Odoo 16+)
        # In Odoo 17/18/19, it's mostly in ir_attachment or specialized tables
        
        conn.commit()
        print("Assets cleared successfully. Restart Odoo to regenerate.")
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    clear_assets()
