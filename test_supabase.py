import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    print("❌ DATABASE_URL not found in .env")
    exit()

try:
    connection = psycopg2.connect(database_url)

    cursor = connection.cursor()
    cursor.execute("SELECT version();")

    version = cursor.fetchone()[0]

    print("✅ Supabase connected successfully!")
    print(version)

    cursor.close()
    connection.close()

except Exception as e:
    print("❌ Supabase connection failed!")
    print(e)