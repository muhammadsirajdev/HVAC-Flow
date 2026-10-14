"""find_customer and customer upsert."""

from psycopg import Connection


def find_customer(conn: Connection, email: str | None, phone: str | None) -> dict | None:
    """Match by email first, then phone. Inputs must already be normalized."""
    if email:
        row = conn.execute("SELECT * FROM customers WHERE lower(email) = %s", (email,)).fetchone()
        if row:
            return row
    if phone:
        return conn.execute("SELECT * FROM customers WHERE phone = %s", (phone,)).fetchone()
    return None


def upsert_customer(conn: Connection, name: str | None, email: str | None, phone: str | None,
                    address: str | None) -> dict:
    """Find by email/phone and fill in missing fields, or create a new customer.

    Existing values are not overwritten: the visitor is not verified, so chat must not
    be able to change a known customer's contact details.
    """
    row = find_customer(conn, email, phone)
    if row is None:
        return conn.execute(
            "INSERT INTO customers (name, email, phone, address) VALUES (%s, %s, %s, %s) RETURNING *",
            (name, email, phone, address),
        ).fetchone()
    return conn.execute(
        "UPDATE customers SET name = COALESCE(name, %s), email = COALESCE(email, %s), "
        "phone = COALESCE(phone, %s), address = COALESCE(address, %s) "
        "WHERE customer_id = %s RETURNING *",
        (name, email, phone, address, row["customer_id"]),
    ).fetchone()
