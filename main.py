import telebot
import os
import subprocess
import time
import threading
from settings import TOKEN, CHAT_ID, CHECK_INTERVAL

# === Настройки ===
FILE_NAME = "containers.txt"
bot = telebot.TeleBot(TOKEN)

# === Утилиты отправки ===
def send_telegram_message(text):
    try:
        bot.send_message(CHAT_ID, text, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def send_telegram_file(file_path):
    try:
        with open(file_path, "rb") as f:
            bot.send_document(CHAT_ID, f)
    except Exception as e:
        print(f"Ошибка отправки файла: {e}")

# === Работа с файлами ===
def save_container(name):
    with open(FILE_NAME, "a", encoding="utf-8") as f:
        f.write(name + "\n")

def load_containers():
    if not os.path.exists(FILE_NAME):
        return []
    with open(FILE_NAME, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def delete_container(name):
    containers = load_containers()
    containers = [c for c in containers if c != name]
    with open(FILE_NAME, "w", encoding="utf-8") as f:
        f.write("\n".join(containers) + ("\n" if containers else ""))

# === Бот ===
@bot.message_handler(commands=['start'])
def handle_start(message):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Добавить", callback_data="add"))
    markup.add(telebot.types.InlineKeyboardButton("Удалить", callback_data="delete"))
    markup.add(telebot.types.InlineKeyboardButton("Показать", callback_data="list"))
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "add":
        bot.send_message(call.message.chat.id, "Введите название контейнера для добавления:")
        bot.register_next_step_handler(call.message, handle_add)
    elif call.data == "delete":
        containers = load_containers()
        if not containers:
            bot.send_message(call.message.chat.id, "Список пуст.")
            return
        markup = telebot.types.InlineKeyboardMarkup()
        for name in containers:
            markup.add(telebot.types.InlineKeyboardButton(name, callback_data=f"remove:{name}"))
        bot.send_message(call.message.chat.id, "Выберите контейнер для удаления:", reply_markup=markup)
    elif call.data == "list":
        containers = load_containers()
        text = "\n".join(containers) if containers else "Список пуст."
        bot.send_message(call.message.chat.id, f"Текущие контейнеры:\n{text}")
    elif call.data.startswith("remove:"):
        name = call.data.split("remove:")[1]
        delete_container(name)
        bot.send_message(call.message.chat.id, f"Контейнер '{name}' удалён.")

def handle_add(message):
    name = message.text.strip()
    if name:
        save_container(name)
        bot.send_message(message.chat.id, f"Контейнер '{name}' добавлен.")
    else:
        bot.send_message(message.chat.id, "Пустое название не добавлено.")

# === Мониторинг ===
def is_container_running(name):
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False

def get_container_logs(name, file_path):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            subprocess.run(
                ["docker", "logs", name],
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True
            )
        return True
    except Exception:
        return False

def monitor_containers():
    previous_states = {}
    while True:
        containers = load_containers()
        for name in containers:
            running = is_container_running(name)
            was_running = previous_states.get(name, True)
            if not running and was_running:
                log_path = f"logs_{name}.txt"
                success = get_container_logs(name, log_path)
                if success:
                    send_telegram_message(f"🚨 Контейнер *{name}* упал! Отправляю логи:")
                    send_telegram_file(log_path)
                    os.remove(log_path)
                else:
                    send_telegram_message(f"🚨 Контейнер *{name}* упал, но не удалось получить логи.")
            previous_states[name] = running
        time.sleep(CHECK_INTERVAL)

# === Старт ===
if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_containers, daemon=True)
    monitor_thread.start()
    bot.polling(none_stop=True)
