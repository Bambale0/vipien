# AmneziaWG Сервер Setup Guide

## Введение

Этот гайд содержит подробные инструкции по настройке AmneziaWG сервера для работы с VPN Telegram ботом. Здесь описаны все ключевые моменты, которые были выявлены и исправлены в процессе разработки проекта.

## Содержание

1. [Требования к системе](#требования-к-системе)
2. [Установка и настройка AmneziaWG](#установка-и-настройка-amneziawg)
3. [Конфигурация сервера](#конфигурация-сервера)
4. [Настройка сети и iptables](#настройка-сети-и-iptables)
5. [Ключевые параметры маскировки](#ключевые-параметры-маскировки)
6. [Проверка и тестирование](#проверка-и-тестирование)
7. [Частые проблемы и решения](#частые-проблемы-и-решения)
8. [Скрипты для автоматизации](#скрипты-для-автоматизации)

## Требования к системе

- **ОС**: Ubuntu 22.04 или 24.04
- **Права**: root или sudo
- **Память**: минимум 1 ГБ
- **Сеть**: статический IP-адрес
- **Порты**: 51820 (UDP) для WireGuard, 8080 (TCP) для вебхука

## Установка и настройка AmneziaWG

### 1. Установка базовых зависимостей

```bash
sudo apt update
sudo apt install -y \
    curl wget git python3 python3-pip python3-venv \
    python3-dev build-essential libssl-dev libffi-dev \
    iptables-persistent net-tools qrencode wireguard-tools \
    linux-headers-$(uname -r)
```

### 2. Установка AmneziaWG

```bash
# Способ 1: через snap (рекомендуется)
sudo snap install amneziawg

# Способ 2: через репозиторий
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:amnezia/ppa
sudo apt update
sudo apt install -y amneziawg
```

### 3. Проверка установки

```bash
# Проверяем доступность команд
awg --version
awg-quick --version
```

## Конфигурация сервера

### 1. Создание директории для конфигов

```bash
sudo mkdir -p /etc/amnezia/amneziawg
```

### 2. Генерация ключей сервера

```bash
# Генерируем приватный ключ
sudo awg genkey | sudo tee /etc/amnezia/amneziawg/private.key

# Генерируем публичный ключ
sudo cat /etc/amnezia/amneziawg/private.key | sudo awg pubkey | sudo tee /etc/amnezia/amneziawg/public.key

# Устанавливаем права
sudo chmod 600 /etc/amnezia/amneziawg/private.key
sudo chmod 644 /etc/amnezia/amneziawg/public.key
```

### 3. Создание конфигурации сервера

**ВАЖНО**: Используйте точные параметры маскировки, как в рабочем проекте:

```bash
# Получаем основной сетевой интерфейс
MAIN_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
SERVER_IP=$(curl -s ifconfig.me)

# Создаем конфиг
sudo tee /etc/amnezia/amneziawg/wg0.conf > /dev/null << EOF
[Interface]
Address = 10.8.1.1/24
ListenPort = 51820
PrivateKey = $(cat /etc/amnezia/amneziawg/private.key)
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $MAIN_INTERFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $MAIN_INTERFACE -j MASQUERADE
Jc = 6
Jmin = 10
Jmax = 50
S1 = 28
S2 = 75
H1 = 1153214260
H2 = 397682404
H3 = 1017619285
H4 = 451273032
EOF

# Устанавливаем права
sudo chmod 600 /etc/amnezia/amneziawg/wg0.conf
```

### 4. Запуск сервера

```bash
# Запускаем интерфейс
sudo awg-quick up wg0

# Проверяем статус
ip link show wg0
ip addr show wg0
```

## Настройка сети и iptables

### 1. Включение IP forwarding

```bash
# Временно включаем
sudo sysctl -w net.ipv4.ip_forward=1

# Делаем постоянным
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 2. Настройка iptables

```bash
# Определяем основной интерфейс
MAIN_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)

# Разрешаем трафик WireGuard
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
sudo iptables -A INPUT -i wg0 -j ACCEPT

# NAT для WireGuard клиентов
sudo iptables -t nat -A POSTROUTING -o $MAIN_INTERFACE -j MASQUERADE
sudo iptables -A FORWARD -i wg0 -o $MAIN_INTERFACE -j ACCEPT
sudo iptables -A FORWARD -i $MAIN_INTERFACE -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT

# Разрешаем вебхук порт
sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT

# Сохраняем правила
sudo netfilter-persistent save
```

## Ключевые параметры маскировки

**КРИТИЧЕСКИ ВАЖНО**: Эти параметры должны точно соответствовать тем, что используются в боте:

```bash
# Параметры маскировки AmneziaWG (обязательные!)
Jc = 6
Jmin = 10
Jmax = 50
S1 = 28
S2 = 75
H1 = 1153214260
H2 = 397682404
H3 = 1017619285
H4 = 451273032
```

Эти параметры обеспечивают:
- Маскировку WireGuard трафика под обычный UDP
- Защиту от DPI (глубокого анализа пакетов)
- Стабильное соединение в условиях блокировок

## Проверка и тестирование

### 1. Проверка работы сервера

```bash
# Проверяем интерфейс
sudo awg show wg0

# Проверяем allowed-ips
sudo awg show wg0 allowed-ips

# Проверяем статистику
sudo awg show wg0 dump
```

### 2. Тестирование подключения

Создайте тестовый конфиг клиента:

```bash
# Генерируем ключи клиента
CLIENT_PRIVATE_KEY=$(awg genkey)
CLIENT_PUBLIC_KEY=$(echo $CLIENT_PRIVATE_KEY | awg pubkey)
CLIENT_IP="10.8.1.2"

# Создаем клиентский конфиг
cat > test_client.conf << EOF
[Interface]
Address = $CLIENT_IP/32
DNS = 94.140.14.14,94.140.15.15
PrivateKey = $CLIENT_PRIVATE_KEY
Jc = 6
Jmin = 10
Jmax = 50
S1 = 28
S2 = 75
H1 = 1153214260
H2 = 397682404
H3 = 1017619285
H4 = 451273032

[Peer]
PublicKey = $(cat /etc/amnezia/amneziawg/public.key)
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = $SERVER_IP:51820
PersistentKeepalive = 25
EOF
```

### 3. Добавление тестового пира

```bash
# Генерируем preshared-key
PSK=$(awg genpsk)

# Добавляем пира
sudo awg set wg0 peer $CLIENT_PUBLIC_KEY preshared-key <(echo $PSK) allowed-ips $CLIENT_IP/32

# Проверяем добавление
sudo awg show wg0 allowed-ips | grep $CLIENT_IP
```

## Частые проблемы и решения

### 1. Конфиги не работают

**Причина**: Несоответствие параметров маскировки между сервером и клиентом.

**Решение**: Убедитесь, что все параметры Jc, Jmin, Jmax, S1, S2, H1-H4 идентичны на сервере и в клиентских конфигах.

### 2. Нет интернета у клиентов

**Причина**: Неправильно настроенный NAT или iptables.

**Решение**:
```bash
# Проверяем NAT правила
sudo iptables -t nat -L POSTROUTING -v

# Проверяем forwarding
cat /proc/sys/net/ipv4/ip_forward
```

### 3. Сервер не принимает подключения

**Причина**: Брандмауэр блокирует порт 51820.

**Решение**:
```bash
# Проверяем правила iptables
sudo iptables -L INPUT -v | grep 51820

# Проверяем открытые порты
sudo netstat -tuln | grep 51820
```

### 4. Ошибки в логах бота

**Причина**: Проблемы с правами доступа к командам awg.

**Решение**:
```bash
# Проверяем права на команды
ls -la $(which awg)
ls -la $(which awg-quick)

# Добавляем права sudo (если нужно)
echo "wg-bot ALL=(ALL) NOPASSWD: /usr/bin/awg, /usr/bin/awg-quick" | sudo tee -a /etc/sudoers
```

## Скрипты для автоматизации

### 1. Скрипт установки (install.sh)

Полный скрипт установки доступен в репозитории: `install.sh`

**ВАЖНО**: Скрипт автоматически:
- Устанавливает все зависимости
- Настраивает AmneziaWG с правильными параметрами маскировки
- Создает systemd сервис для бота
- Настраивает iptables и IP forwarding
- Генерирует ключи сервера

### 2. Скрипт проверки пиров (verify_and_fix_peers.py)

```bash
# Проверка и восстановление пиров
python3 scripts/verify_and_fix_peers.py
```

Этот скрипт:
- Сравнивает пиров в базе данных с реальными пироми на сервере
- Автоматически добавляет недостающих пиров
- Восстанавливает конфигурацию сервера при необходимости

### 3. Скрипт мониторинга

```bash
#!/bin/bash
# monitor_wg.sh

while true; do
    # Проверяем активность интерфейса
    if ! ip link show wg0 &> /dev/null; then
        echo "$(date): wg0 interface down, restarting..."
        sudo awg-quick up wg0
    fi
    
    # Проверяем количество пиров
    PEER_COUNT=$(sudo awg show wg0 | grep -c "peer:")
    echo "$(date): Active peers: $PEER_COUNT"
    
    sleep 60
done
```

### 4. Скрипт быстрого развертывания

```bash
#!/bin/bash
# quick_setup.sh

echo "🚀 Быстрое развертывание AmneziaWG сервера..."

# 1. Установка зависимостей
sudo apt update && sudo apt install -y curl wget git python3 python3-pip python3-venv iptables-persistent net-tools qrencode wireguard-tools

# 2. Установка AmneziaWG
sudo snap install amneziawg

# 3. Генерация ключей
sudo mkdir -p /etc/amnezia/amneziawg
sudo awg genkey | sudo tee /etc/amnezia/amneziawg/private.key
sudo cat /etc/amnezia/amneziawg/private.key | sudo awg pubkey | sudo tee /etc/amnezia/amneziawg/public.key
sudo chmod 600 /etc/amnezia/amneziawg/private.key

# 4. Создание конфига
MAIN_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
SERVER_IP=$(curl -s ifconfig.me)

sudo tee /etc/amnezia/amneziawg/wg0.conf > /dev/null << EOF
[Interface]
Address = 10.8.1.1/24
ListenPort = 51820
PrivateKey = $(cat /etc/amnezia/amneziawg/private.key)
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $MAIN_INTERFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $MAIN_INTERFACE -j MASQUERADE
Jc = 6
Jmin = 10
Jmax = 50
S1 = 28
S2 = 75
H1 = 1153214260
H2 = 397682404
H3 = 1017619285
H4 = 451273032
EOF

# 5. Настройка сети
sudo sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf

# 6. iptables
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
sudo iptables -A INPUT -i wg0 -j ACCEPT
sudo iptables -t nat -A POSTROUTING -o $MAIN_INTERFACE -j MASQUERADE
sudo iptables -A FORWARD -i wg0 -o $MAIN_INTERFACE -j ACCEPT
sudo iptables -A FORWARD -i $MAIN_INTERFACE -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo netfilter-persistent save

# 7. Запуск сервера
sudo awg-quick up wg0

echo "✅ AmneziaWG сервер готов!"
echo "🌐 Серверный IP: $SERVER_IP"
echo "🔑 Публичный ключ: $(cat /etc/amnezia/amneziawg/public.key)"
```

## Интеграция с ботом

### 1. Настройка .env файла

```bash
# Обязательные переменные для бота
WG_SERVER_PUBLIC_KEY="ваш_публичный_ключ_сервера"
WG_ENDPOINT="ваш_IP:51820"
WG_DNS="94.140.14.14,94.140.15.15"
WG_JC=6
WG_JMIN=10
WG_JMAX=50
WG_S1=28
WG_S2=75
WG_H1=1153214260
WG_H2=397682404
WG_H3=1017619285
WG_H4=451273032
```

**ВАЖНО**: Все параметры маскировки (Jc, Jmin, Jmax, S1, S2, H1-H4) должны точно соответствовать тем, что указаны в конфигурации сервера.

### 2. Проверка совместимости

**Шаг 1**: Проверьте публичный ключ сервера
```bash
# На сервере
cat /etc/amnezia/amneziawg/public.key

# В .env файле бота
echo $WG_SERVER_PUBLIC_KEY
```

**Шаг 2**: Сравните параметры маскировки
```bash
# На сервере (из конфига)
grep -E "Jc|Jmin|Jmax|S1|S2|H1|H2|H3|H4" /etc/amnezia/amneziawg/wg0.conf

# В коде бота (config.py)
grep -E "WG_JC|WG_JMIN|WG_JMAX|WG_S1|WG_S2|WG_H1|WG_H2|WG_H3|WG_H4" bot/config.py
```

**Шаг 3**: Проверьте endpoint
```bash
# Серверный IP
curl -s ifconfig.me

# Endpoint в .env
echo $WG_ENDPOINT
```

### 3. Тестирование бота

```bash
# 1. Устанавливаем зависимости
cd /path/to/bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Запускаем бота
python3 bot/bot.py

# 3. Проверяем логи
tail -f logs/bot.log

# 4. Тестируем генерацию конфига
# Отправьте боту команду /start и создайте тестовую подписку
```

### 4. Тестирование конфигурации

**Тест 1**: Проверка генерации конфига
```bash
# Запустите бота и создайте тестовую подписку
# Проверьте сгенерированный конфиг на соответствие параметрам:
grep -E "Jc|Jmin|Jmax|S1|S2|H1|H2|H3|H4" сгенерированный_конфиг.conf
```

**Тест 2**: Проверка добавления пира на сервер
```bash
# После генерации конфига проверьте:
sudo awg show wg0 allowed-ips | grep "IP_клиента"
```

**Тест 3**: Проверка подключения
```bash
# Используйте сгенерированный конфиг для подключения
# Проверьте ping до сервера и интернет
ping 10.8.1.1
curl ifconfig.me
```

### 5. Автоматическое тестирование

```bash
#!/bin/bash
# test_bot_integration.sh

echo "🔍 Тестирование интеграции бота с AmneziaWG..."

# Проверка публичного ключа
SERVER_KEY=$(cat /etc/amnezia/amneziawg/public.key)
BOT_KEY=$(grep WG_SERVER_PUBLIC_KEY .env | cut -d'=' -f2)
if [ "$SERVER_KEY" = "$BOT_KEY" ]; then
    echo "✅ Публичные ключи совпадают"
else
    echo "❌ Публичные ключи не совпадают"
    echo "Сервер: $SERVER_KEY"
    echo "Бот: $BOT_KEY"
fi

# Проверка параметров маскировки
echo "📋 Проверка параметров маскировки..."
for param in Jc Jmin Jmax S1 S2 H1 H2 H3 H4; do
    SERVER_VAL=$(grep "^$param" /etc/amnezia/amneziawg/wg0.conf | cut -d'=' -f2)
    BOT_VAL=$(grep "WG_$param" bot/config.py | cut -d'=' -f2 | tr -d ' ')
    if [ "$SERVER_VAL" = "$BOT_VAL" ]; then
        echo "✅ $param: $SERVER_VAL"
    else
        echo "❌ $param не совпадает: сервер=$SERVER_VAL, бот=$BOT_VAL"
    fi
done

# Проверка endpoint
SERVER_IP=$(curl -s ifconfig.me)
BOT_ENDPOINT=$(grep WG_ENDPOINT .env | cut -d'=' -f2)
if [[ "$BOT_ENDPOINT" == *"$SERVER_IP"* ]]; then
    echo "✅ Endpoint содержит правильный IP"
else
    echo "❌ Endpoint не содержит правильный IP"
    echo "Сервер IP: $SERVER_IP"
    echo "Bot endpoint: $BOT_ENDPOINT"
fi

echo "🏁 Тестирование завершено"
```

## Заключение

Ключевые моменты для успешной работы:

1. **Точные параметры маскировки** - должны быть идентичны на сервере и в боте
2. **Правильная настройка сети** - IP forwarding и iptables
3. **Права доступа** - бот должен иметь доступ к командам awg через sudo
4. **Проверка конфигурации** - регулярно проверяйте работу сервера

Если следовать этим инструкциям, сервер будет работать стабильно и генерировать рабочие конфиги для клиентов.