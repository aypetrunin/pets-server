from fastapi import FastAPI
import asyncpg
import asyncssh
from dotenv import load_dotenv
import os

app = FastAPI()

# Загрузка переменных окружения
load_dotenv()

# Конфигурация SSH туннеля
SSH_CONFIG = {
    'host': os.getenv('SSH_HOST'),
    'username': os.getenv('SSH_USERNAME'),
    'client_keys': [os.getenv('SSH_CLIENT_KEYS')],
    'passphrase': os.getenv('SSH_PASSPHRASE')
}

# Конфигурация для базы данных
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', 5432))
}

async def create_ssh_tunnel():
    """Создание SSH туннеля для подключения к базе данных"""
    try:
        conn = await asyncssh.connect(**SSH_CONFIG)
        tunnel = await conn.forward_local_port('', 15432,
                                             DATABASE_CONFIG['host'], DATABASE_CONFIG['port'])
        return conn, tunnel
    except Exception as e:
        raise ValueError(f"Ошибка при создании SSH-туннеля: {str(e)}")

@app.on_event("startup")
async def startup():
    """Инициализация подключения при запуске"""
    app.state.ssh_conn, app.state.tunnel = await create_ssh_tunnel()
    local_config = DATABASE_CONFIG.copy()
    local_config['host'] = 'localhost'
    local_config['port'] = 15432
    app.state.pool = await asyncpg.create_pool(**local_config)

@app.on_event("shutdown")
async def shutdown():
    """Закрытие соединений при завершении работы"""
    await app.state.pool.close()
    app.state.tunnel.close()
    app.state.ssh_conn.close()

@app.get("/pets/{user_phone}")
async def get_user_pets(user_phone: str):
    """
    Эндпоинт для получения информации о питомцах пользователя по номеру телефона
    """
    try:
        async with app.state.pool.acquire() as connection:
            result = await connection.fetchval('SELECT get_user_pets_by_user_phone($1)', user_phone)
            if result is not None:
                return result
            else:
                return {"status": "error", "message": "Пользователь не найден"}
    except asyncpg.PostgresError as e:
        return {"status": "error", "message": f"Ошибка базы данных: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Неизвестная ошибка: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)