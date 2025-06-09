# verify_data.py
import asyncio
import sqlite3

async def check_esprit_count():
    # Connect to the SQLite database directly
    conn = sqlite3.connect('nyxa.db')
    cursor = conn.cursor()
    
    # Count Esprits
    cursor.execute("SELECT COUNT(*) FROM espritdata")
    count = cursor.fetchone()[0]
    
    print(f"Total Esprits in database: {count}")
    
    # Show a few examples
    cursor.execute("SELECT esprit_id, name, rarity FROM espritdata LIMIT 5")
    examples = cursor.fetchall()
    
    if examples:
        print("\nFirst 5 Esprits:")
        for esprit in examples:
            print(f"  - {esprit[0]}: {esprit[1]} ({esprit[2]})")
    
    # Check if any tables are empty
    for table in ['user', 'useresprit']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        table_count = cursor.fetchone()[0]
        print(f"\n{table} table has {table_count} rows")
    
    conn.close()

if __name__ == "__main__":
    asyncio.run(check_esprit_count())
