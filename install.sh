#!/bin/bash

# =============================================================================
# Скрипт установки VPN бота с AmneziaWG на Ubuntu 24.04
# =============================================================================

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для вывода
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка root прав
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "Этот скрипт должен быть запущен с root правами"
        print_info "Запустите: sudo bash install.sh"
        exit 1
    fi
}

# Проверка Ubuntu 24.04
check_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        if [[ "$VERSION_ID" != "24.04" && "$VERSION_ID" != "22.04" ]]; then
            print_warning "Рекомендуется Ubuntu 24.04 или 22.04. Текущая версия: $VERSION_ID"
            read -p "Продолжить установку? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    else
        print_warning "Не удалось определить версию ОС"
    fi
}

# Установка базовых зависимостей
install_base_deps() {
    print_info "Обновление пакетов и установка базовых зависимостей..."
    apt-get update
    apt-get install -y \
        curl \
        wget \
        git \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        libssl-dev \
        libffi-dev \
        iptables-persistent \
        net-tools \
        qrencode \
        wireguard-tools \
        linux-headers-$(uname -r)
    print_success "Базовые зависимости установлены"
}

# Установка AmneziaWG
install_amneziawg() {
    print_info "Установка AmneziaWG..."
    
    # Проверяем, установлен ли уже amneziawg
    if command -v awg &> /dev/null; then
        print_success "AmneziaWG уже установлен"
        return
    fi
    
    # Добавляем репозиторий AmneziaWG
    print_info "Добавление репозитория AmneziaWG..."
    
    # Установка через snap или из исходников
    # На Ubuntu 24.04 используем snap
    if command -v snap &> /dev/null; then
        snap install amneziawg
    else
        # Альтернативная установка из GitHub
        print_info "Установка AmneziaWG из репозитория..."
        cd /tmp
        git clone https://github.com/amnezia-vpn/amneziawg-go.git 2>/dev/null || true
        
        # Установка через apt если доступно
        apt-get install -y software-properties-common
        add-apt-repository -y ppa:amnezia/ppa 2>/dev/null || true
        apt-get update
        apt-get install -y amneziawg 2>/dev/null || true
    fi
    
    # Проверяем установку
    if command -v awg &> /dev/null; then
        print_success "AmneziaWG успешно установлен"
    else
        print_warning "AmneziaWG может быть не полностью установлен, но будем использовать wg"
    fi
}

# Настройка IP forwarding
setup_ip_forwarding() {
    print_info "Настройка IP forwarding..."
    
    # Включаем IP forwarding
    sysctl -w net.ipv4.ip_forward=1
    
    # Делаем настройку постоянной
    if ! grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf; then
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi
    
    # Применяем настройки
    sysctl -p
    
    print_success "IP forwarding настроен"
}

# Настройка iptables
setup_iptables() {
    print_info "Настройка iptables..."
    
    # Определяем основной сетевой интерфейс
    MAIN_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
    if [[ -z "$MAIN_INTERFACE" ]]; then
        MAIN_INTERFACE="eth0"
    fi
    
    print_info "Основной сетевой интерфейс: $MAIN_INTERFACE"
    
    # Разрешаем трафик WireGuard
    iptables -A INPUT -p udp --dport 51820 -j ACCEPT
    iptables -A INPUT -i wg0 -j ACCEPT
    
    # NAT для WireGuard клиентов
    iptables -t nat -A POSTROUTING -o $MAIN_INTERFACE -j MASQUERADE
    iptables -A FORWARD -i wg0 -o $MAIN_INTERFACE -j ACCEPT
    iptables -A FORWARD -i $MAIN_INTERFACE -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT
    
    # Разрешаем вебхук порт
    iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
    
    # Сохраняем правила
    netfilter-persistent save
    
    print_success "iptables настроены и сохранены"
}

# Создание директории для бота
setup_bot_directory() {
    print_info "Настройка директории бота..."
    
    BOT_DIR="/root/vipien"
    
    # Создаем директорию
    mkdir -p $BOT_DIR
    mkdir -p $BOT_DIR/logs
    mkdir -p $BOT_DIR/wg_configs
    
    # Клонируем репозиторий бота
    print_info "Клонирование репозитория бота..."
    cd /tmp
    git clone https://github.com/Bambale0/vipien.git 2>/dev/null || git clone git@github.com:Bambale0/vipien.git 2>/dev/null || true
    
    if [[ -d "/tmp/vipien" ]]; then
        cd /tmp/vipien
        cp -r bot $BOT_DIR/
        cp -r scripts $BOT_DIR/ 2>/dev/null || true
        cp requirements.txt $BOT_DIR/
        cp start.sh $BOT_DIR/
        cp stop.sh $BOT_DIR/
        
        # Чистим временные файлы
        rm -rf /tmp/vipien
        print_success "Файлы бота склонированы из репозитория"
    else
        # Fallback - создаем структуру вручную если git clone не сработал
        print_warning "Не удалось клонировать репозиторий, создаем структуру вручную..."
        mkdir -p $BOT_DIR/bot
        mkdir -p $BOT_DIR/scripts
    fi
    
    # Устанавливаем права
    chown -R root:root $BOT_DIR
    chmod -R 755 $BOT_DIR
    chmod 700 $BOT_DIR/wg_configs
    
    print_success "Директория бота настроена: $BOT_DIR"
}

# Создание виртуального окружения Python
setup_python_venv() {
    print_info "Настройка Python виртуального окружения..."
    
    cd /root/vipien
    
    # Создаем виртуальное окружение
    python3 -m venv venv
    
    # Активируем и устанавливаем зависимости
    source venv/bin/activate
    pip install --upgrade pip
    pip install pynacl==1.5.0
    pip install -r requirements.txt
    
    print_success "Python виртуальное окружение настроено"
}

# Создание systemd сервиса
create_systemd_service() {
    print_info "Создание systemd сервиса..."
    
    cat > /etc/systemd/system/wg-bot.service << 'EOF'
[Unit]
Description=WireGuard VPN Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/vipien
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/root/vipien/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/root/vipien/venv/bin/python /root/vipien/bot/bot.py
ExecStop=/bin/bash /root/vipien/stop.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # Перезагружаем systemd
    systemctl daemon-reload
    systemctl enable wg-bot.service
    
    print_success "Systemd сервис создан и включен"
}

# Настройка AmneziaWG сервера
setup_amneziawg_server() {
    print_info "Настройка AmneziaWG сервера..."
    
    # Создаем директорию для конфигов
    mkdir -p /etc/amnezia/amneziawg
    
    # Генерируем ключи сервера если их нет
    if [[ ! -f /etc/amnezia/amneziawg/private.key ]]; then
        print_info "Генерация ключей сервера..."
        
        # Генерируем приватный ключ
        if command -v awg &> /dev/null; then
            awg genkey > /etc/amnezia/amneziawg/private.key
            cat /etc/amnezia/amneziawg/private.key | awg pubkey > /etc/amnezia/amneziawg/public.key
        else
            # Fallback на wg
            wg genkey > /etc/amnezia/amneziawg/private.key
            cat /etc/amnezia/amneziawg/private.key | wg pubkey > /etc/amnezia/amneziawg/public.key
        fi
        
        chmod 600 /etc/amnezia/amneziawg/private.key
        chmod 644 /etc/amnezia/amneziawg/public.key
    fi
    
    # Получаем публичный ключ сервера
    SERVER_PRIVATE_KEY=$(cat /etc/amnezia/amneziawg/private.key)
    SERVER_PUBLIC_KEY=$(cat /etc/amnezia/amneziawg/public.key)
    
    print_info "Публичный ключ сервера: $SERVER_PUBLIC_KEY"
    
    # Определяем основной сетевой интерфейс
    MAIN_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
    if [[ -z "$MAIN_INTERFACE" ]]; then
        MAIN_INTERFACE="eth0"
    fi
    
    # Получаем IP сервера
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    
    # Создаем конфиг сервера
    cat > /etc/amnezia/amneziawg/wg0.conf << EOF
[Interface]
Address = 10.8.1.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIVATE_KEY
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

    chmod 600 /etc/amnezia/amneziawg/wg0.conf
    
    print_success "Конфигурация AmneziaWG сервера создана"
    print_info "Путь к конфигу: /etc/amnezia/amneziawg/wg0.conf"
    print_info "Публичный ключ сервера: $SERVER_PUBLIC_KEY"
    print_info "IP сервера: $SERVER_IP"
    
    # Сохраняем информацию о сервере
    cat > /root/vipien/server_info.txt << EOF
AmneziaWG Server Information
=============================
Server IP: $SERVER_IP
Public Key: $SERVER_PUBLIC_KEY
Endpoint: $SERVER_IP:51820
Config Path: /etc/amnezia/amneziawg/wg0.conf
Interface: wg0
Network: 10.8.1.0/24

AmneziaWG Masking Parameters:
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

    print_success "Информация о сервере сохранена в /root/vipien/server_info.txt"
}

# Запуск AmneziaWG сервера
start_amneziawg() {
    print_info "Запуск AmneziaWG сервера..."
    
    # Проверяем, запущен ли уже
    if ip link show wg0 &> /dev/null; then
        print_warning "Интерфейс wg0 уже существует, останавливаем..."
        awg-quick down wg0 2>/dev/null || wg-quick down wg0 2>/dev/null || true
    fi
    
    # Запускаем интерфейс
    if command -v awg-quick &> /dev/null; then
        awg-quick up wg0
        print_success "AmneziaWG сервер запущен (awg-quick)"
    elif command -v wg-quick &> /dev/null; then
        wg-quick up wg0
        print_success "WireGuard сервер запущен (wg-quick)"
    else
        print_error "Не найдены awg-quick или wg-quick"
        exit 1
    fi
    
    # Проверяем статус
    if ip link show wg0 &> /dev/null; then
        print_success "Интерфейс wg0 активен"
        ip addr show wg0 | grep "inet "
    else
        print_error "Не удалось активировать интерфейс wg0"
        exit 1
    fi
}

# Настройка .env файла
setup_env() {
    print_info "Настройка .env файла..."
    
    cd /root/vipien
    
    if [[ -f ".env" ]]; then
        print_warning ".env файл уже существует"
        read -p "Перезаписать? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Сохраняем существующий .env"
            return
        fi
    fi
    
    # Получаем IP сервера
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    
    echo ""
    echo "=========================================="
    echo "Настройка переменных окружения"
    echo "=========================================="
    echo ""
    
    read -p "Введите Telegram Bot Token: " BOT_TOKEN
    read -p "Введите YooKassa Shop ID: " YOOKASSA_SHOP_ID
    read -p "Введите YooKassa Secret Key: " YOOKASSA_SECRET_KEY
    read -p "Введите ID администраторов (через запятую): " ADMIN_IDS
    read -p "Введите домен для webhook [vpn.chillcreative.ru]: " WEBHOOK_DOMAIN
    WEBHOOK_DOMAIN=${WEBHOOK_DOMAIN:-vpn.chillcreative.ru}
    
    # Получаем публичный ключ сервера
    SERVER_PUBLIC_KEY=""
    if [[ -f /etc/amnezia/amneziawg/public.key ]]; then
        SERVER_PUBLIC_KEY=$(cat /etc/amnezia/amneziawg/public.key)
    fi
    
    cat > .env << EOF
# Telegram Bot
BOT_TOKEN=$BOT_TOKEN

# YooKassa
YOOKASSA_SHOP_ID=$YOOKASSA_SHOP_ID
YOOKASSA_SECRET_KEY=$YOOKASSA_SECRET_KEY
YOOKASSA_TEST_MODE=true

# Admins
ADMIN_IDS=$ADMIN_IDS

# Links
SUPPORT_LINK=https://t.me/support
CHANNEL_LINK=

# WireGuard/AmneziaWG
WG_INTERFACE=wg0
WG_CONFIG_PATH=/etc/amnezia/amneziawg/wg0.conf
WG_ENDPOINT=$SERVER_IP:51820
WG_DNS=94.140.14.14,94.140.15.15

# Webhook
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
WEBHOOK_PATH=/webhook/yookassa
WEBHOOK_URL=https://$WEBHOOK_DOMAIN/webhook/yookassa
EOF

    chmod 600 .env
    print_success ".env файл создан"
    print_info "Путь: /root/vipien/.env"
    
    # Обновляем конфиг сервера с новым endpoint если нужно
    if [[ -n "$SERVER_PUBLIC_KEY" ]]; then
        print_info "Публичный ключ сервера: $SERVER_PUBLIC_KEY"
    fi
}

# Установка и настройка Nginx (опционально)
setup_nginx() {
    print_info "Настройка Nginx..."
    
    read -p "Установить и настроить Nginx с SSL? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Пропускаем установку Nginx"
        return
    fi
    
    # Устанавливаем Nginx и Certbot
    apt-get install -y nginx certbot python3-certbot-nginx
    
    # Получаем домен
    read -p "Введите домен для SSL: " DOMAIN
    
    # Создаем конфиг Nginx
    cat > /etc/nginx/sites-available/wg-bot << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location /webhook/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8080/health;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }
}
EOF
    
    # Активируем сайт
    ln -sf /etc/nginx/sites-available/wg-bot /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    
    # Проверяем конфиг
    nginx -t
    
    # Перезапускаем Nginx
    systemctl restart nginx
    systemctl enable nginx
    
    # Получаем SSL сертификат
    print_info "Получение SSL сертификата..."
    certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN
    
    print_success "Nginx настроен с SSL"
}

# Запуск бота
start_bot() {
    print_info "Запуск VPN бота..."
    
    cd /root/vipien
    
    # Запускаем через systemd
    systemctl start wg-bot
    
    sleep 3
    
    # Проверяем статус
    if systemctl is-active --quiet wg-bot; then
        print_success "VPN бот успешно запущен!"
        systemctl status wg-bot --no-pager
    else
        print_error "Не удалось запустить бота"
        print_info "Проверьте логи: journalctl -u wg-bot -n 50"
    fi
}

# Главная функция
main() {
    echo "=========================================="
    echo "  Установка VPN бота с AmneziaWG"
    echo "  Ubuntu 24.04"
    echo "=========================================="
    echo ""
    
    check_root
    check_os
    
    print_info "Начало установки..."
    
    install_base_deps
    install_amneziawg
    setup_ip_forwarding
    setup_bot_directory
    setup_python_venv
    setup_amneziawg_server
    setup_iptables
    setup_env
    create_systemd_service
    setup_nginx
    
    echo ""
    echo "=========================================="
    print_success "Установка завершена!"
    echo "=========================================="
    echo ""
    echo "Информация о сервере:"
    cat /root/vipien/server_info.txt 2>/dev/null || print_warning "Файл server_info.txt не найден"
    echo ""
    
    read -p "Запустить бота сейчас? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        start_bot
    fi
    
    echo ""
    echo "=========================================="
    echo "Полезные команды:"
    echo "  systemctl status wg-bot    - статус бота"
    echo "  systemctl start wg-bot     - запуск бота"
    echo "  systemctl stop wg-bot      - остановка бота"
    echo "  journalctl -u wg-bot -f    - просмотр логов"
    echo "  awg show                   - статус WireGuard"
    echo "=========================================="
}

# Запускаем главную функцию
main "$@"
