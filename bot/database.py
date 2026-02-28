import aiosqlite
import json
from datetime import datetime, timedelta
from config import config

class Database:
    def __init__(self):
        self.db_path = config.DB_PATH
    
    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    configs_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица подписок
            await db.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plan_id TEXT,
                    price INTEGER,
                    status TEXT DEFAULT 'active',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица конфигов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    config_name TEXT,
                    private_key TEXT,
                    public_key TEXT,
                    preshared_key TEXT,
                    address TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица платежей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subscription_id INTEGER,
                    payment_id TEXT UNIQUE,
                    amount INTEGER,
                    plan_id TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    paid_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
                )
            ''')
            
            await db.commit()
    
    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM users WHERE user_id = ?', (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def create_user(self, user_id: int, username: str, first_name: str, last_name: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            await db.commit()
    
    async def get_active_subscription(self, user_id: int):
        """Получает активную подписку пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM subscriptions 
                WHERE user_id = ? AND status = 'active' AND expires_at > ?
                ORDER BY expires_at DESC LIMIT 1
            ''', (user_id, datetime.now())) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def create_subscription(self, user_id: int, plan_id: str, price: int, days: int):
        """Создает новую подписку"""
        started_at = datetime.now()
        expires_at = started_at + timedelta(days=days)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO subscriptions (user_id, plan_id, price, started_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, plan_id, price, started_at, expires_at))
            await db.commit()
            return cursor.lastrowid
    
    async def create_payment(self, user_id: int, subscription_id: int, payment_id: str, amount: int, plan_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO payments (user_id, subscription_id, payment_id, amount, plan_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, subscription_id, payment_id, amount, plan_id))
            await db.commit()
    
    async def confirm_payment(self, payment_id: str):
        """Подтверждает оплату и активирует подписку"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE payments 
                SET status = 'succeeded', paid_at = ?
                WHERE payment_id = ?
            ''', (datetime.now(), payment_id))
            await db.commit()
    
    async def add_config(self, user_id: int, config_name: str, private_key: str, 
                        public_key: str, preshared_key: str, address: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO configs (user_id, config_name, private_key, public_key, preshared_key, address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, config_name, private_key, public_key, preshared_key, address))
            
            await db.execute('''
                UPDATE users SET configs_count = configs_count + 1 WHERE user_id = ?
            ''', (user_id,))
            
            await db.commit()
    
    async def get_user_configs(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM configs WHERE user_id = ? AND is_active = TRUE', (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_configs_count(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT configs_count FROM users WHERE user_id = ?', (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def delete_user_configs(self, user_id: int):
        """Удаляет все конфиги пользователя из базы данных и файловой системы"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем список конфигов пользователя
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT config_name FROM configs WHERE user_id = ?', (user_id,)
            ) as cursor:
                configs = await cursor.fetchall()
            
            # Удаляем файлы конфигов
            import os
            for config_row in configs:
                config_name = config_row['config_name']
                config_path = f"wg_configs/{config_name}.conf"
                qr_path = f"wg_configs/{config_name}.png"
                
                if os.path.exists(config_path):
                    os.remove(config_path)
                if os.path.exists(qr_path):
                    os.remove(qr_path)
            
            # Удаляем записи из базы данных
            await db.execute('DELETE FROM configs WHERE user_id = ?', (user_id,))
            await db.execute('UPDATE users SET configs_count = 0 WHERE user_id = ?', (user_id,))
            await db.commit()
    
    async def get_subscription_stats(self):
        """Статистика подписок для админов"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Всего пользователей
            async with db.execute('SELECT COUNT(*) FROM users') as cursor:
                total_users = (await cursor.fetchone())[0]
            
            # Активных подписок
            async with db.execute(
                'SELECT COUNT(*) FROM subscriptions WHERE status = ? AND expires_at > ?',
                ('active', datetime.now())
            ) as cursor:
                active_subs = (await cursor.fetchone())[0]
            
            # Выручка
            async with db.execute(
                "SELECT SUM(amount) FROM payments WHERE status = 'succeeded'"
            ) as cursor:
                revenue = (await cursor.fetchone())[0] or 0
            
            return {
                'total_users': total_users,
                'active_subscriptions': active_subs,
                'total_revenue': revenue
            }

db = Database()