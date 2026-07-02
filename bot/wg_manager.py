import base64
import contextlib
import datetime
import fcntl
import logging
import os
import subprocess
import tempfile
import time
from typing import Optional, Tuple

from config import config
from nacl.public import PrivateKey


class WireGuardManager:
    def __init__(self):
        self.configs_dir = "wg_configs"
        os.makedirs(self.configs_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def generate_keypair(self) -> Tuple[str, str]:
        """Генерирует приватный и публичный ключи WireGuard с использованием pynacl"""
        try:
            # Генерируем приватный ключ
            private_key_obj = PrivateKey.generate()
            private_key = base64.b64encode(bytes(private_key_obj)).decode()

            # Получаем публичный ключ
            public_key_obj = private_key_obj.public_key
            public_key = base64.b64encode(bytes(public_key_obj)).decode()

            return private_key, public_key
        except Exception as e:
            print(f"Error generating keypair with pynacl: {e}")
            # Fallback на системную команду wg
            private_key = (
                subprocess.check_output(["sudo", "wg", "genkey"]).decode().strip()
            )
            public_key = (
                subprocess.check_output(
                    ["sudo", "wg", "pubkey"], input=private_key.encode()
                )
                .decode()
                .strip()
            )
            return private_key, public_key

    def generate_preshared_key(self) -> str:
        """Генерирует предварительный общий ключ"""
        try:
            # Генерируем 32 случайных байта и кодируем в base64
            psk_bytes = os.urandom(32)
            return base64.b64encode(psk_bytes).decode()
        except Exception as e:
            print(f"Error generating PSK: {e}")
            # Fallback на системную команду wg
            return subprocess.check_output(["sudo", "wg", "genpsk"]).decode().strip()

    def get_server_public_key(self) -> str:
        """Получает публичный ключ сервера AmneziaWG"""
        return config.WG_SERVER_PUBLIC_KEY

    def _get_server_config_path(self) -> str:
        return config.WG_CONFIG_PATH or "/etc/amnezia/amneziawg/wg0.conf"

    def _get_config_allowed_ips(self):
        """Возвращает клиентские IP, уже сохраненные в server config."""
        server_config_path = self._get_server_config_path()
        try:
            try:
                read_proc = subprocess.run(
                    ["sudo", "cat", server_config_path],
                    capture_output=True,
                    text=True,
                )
                if read_proc.returncode == 0:
                    config_content = read_proc.stdout
                else:
                    with open(server_config_path, "r") as f:
                        config_content = f.read()
            except Exception:
                with open(server_config_path, "r") as f:
                    config_content = f.read()

            used_ips = set()
            for line in config_content.splitlines():
                stripped = line.strip()
                if not stripped.startswith("AllowedIPs") or "=" not in stripped:
                    continue
                _, value = stripped.split("=", 1)
                for entry in value.split(","):
                    ip = entry.strip().split("/")[0]
                    if ip.startswith("10.8.1."):
                        used_ips.add(ip)
            return used_ips
        except Exception as e:
            self.logger.debug(f"Failed to read saved allowed IPs: {e}")
            return set()

    @staticmethod
    def _allowed_ip_is_present(output: str, public_key: str, allowed_ip: str) -> bool:
        expected_ip = f"{allowed_ip}/32"
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0] != public_key:
                continue
            allowed_ips = " ".join(parts[1:]).replace(",", " ").split()
            return expected_ip in allowed_ips
        return False

    def get_next_ip(self) -> Optional[str]:
        """Находит следующий свободный IP в сети 10.8.1.0/24"""
        try:
            # Получаем список всех allowed-ips из awg (AmneziaWG)
            output = (
                subprocess.check_output(
                    ["sudo", "awg", "show", config.WG_INTERFACE, "allowed-ips"],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )

            used_ips = set()

            # Разбираем вывод команды awg show wg0 allowed-ips
            # Формат: публичный_ключ<TAB>IP/маска
            for line in output.split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        ip_entry = parts[1].strip()
                        if ip_entry != "(none)" and "/" in ip_entry:
                            ip = ip_entry.split("/")[0].strip()
                            if ip.startswith("10.8.1."):
                                used_ips.add(ip)

            # Также проверяем IP в базе данных
            try:
                import sqlite3

                conn = sqlite3.connect("wg_bot.db")
                cursor = conn.cursor()
                cursor.execute("SELECT address FROM configs")
                db_ips = [row[0] for row in cursor.fetchall()]
                conn.close()
                used_ips.update(db_ips)
            except Exception as db_error:
                print(f"Database check error: {db_error}")

            used_ips.update(self._get_config_allowed_ips())

            # Ищем свободный IP в диапазоне 10.8.1.2 - 10.8.1.254
            for i in range(2, 255):
                ip = f"10.8.1.{i}"
                if ip not in used_ips:
                    print(f"Found free IP: {ip}")
                    return ip

            print("No free IPs found in range 10.8.1.2-10.8.1.254")
            return None

        except Exception as e:
            print(f"Error getting next IP from awg: {e}")
            # Fallback - генерируем случайный IP с проверкой в базе данных
            import sqlite3

            used_ips = self._get_config_allowed_ips()
            try:
                conn = sqlite3.connect("wg_bot.db")
                cursor = conn.cursor()
                cursor.execute("SELECT address FROM configs")
                used_ips.update(row[0] for row in cursor.fetchall())
                conn.close()
            except Exception:
                pass

            for i in range(2, 255):
                ip = f"10.8.1.{i}"
                if ip not in used_ips:
                    print(f"Using fallback free IP: {ip}")
                    return ip

            return None

    def generate_config(self, user_id: int, config_num: int) -> dict:
        """Генерирует полный конфиг AmneziaWG для пользователя"""
        private_key, public_key = self.generate_keypair()
        preshared_key = self.generate_preshared_key()
        address = self.get_next_ip()
        if address is None:
            raise RuntimeError("No free WireGuard client IPs available")
        server_public_key = self.get_server_public_key()

        config_name = f"user_{user_id}_{config_num}"

        # Клиентский конфиг с параметрами маскировки AmneziaWG (совпадает с сервером)
        # Форматирование как в рабочем конфиге: пробелы вокруг = и IPv6 в AllowedIPs
        client_config = f"""[Interface]
Address = {address}/32
DNS = {config.WG_DNS}
PrivateKey = {private_key}
Jc = {config.WG_JC}
Jmin = {config.WG_JMIN}
Jmax = {config.WG_JMAX}
S1 = {config.WG_S1}
S2 = {config.WG_S2}
H1 = {config.WG_H1}
H2 = {config.WG_H2}
H3 = {config.WG_H3}
H4 = {config.WG_H4}

[Peer]
PublicKey = {server_public_key}
PresharedKey = {preshared_key}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {config.WG_ENDPOINT}
PersistentKeepalive = 25
"""

        # Сохраняем конфиг
        config_path = os.path.join(self.configs_dir, f"{config_name}.conf")
        with open(config_path, "w") as f:
            f.write(client_config)
        try:
            os.chmod(config_path, 0o600)
        except Exception:
            # best-effort
            pass

        # Добавляем пира в контейнер amnezia-awg (с блокировкой внутри)
        self.add_peer_to_amnezia_awg(public_key, preshared_key, address)

        return {
            "config_name": config_name,
            "private_key": private_key,
            "public_key": public_key,
            "preshared_key": preshared_key,
            "address": address,
            "config_text": client_config,
            "config_path": config_path,
        }

    def add_peer_to_amnezia_awg(
        self, public_key: str, preshared_key: str, allowed_ip: str
    ):
        """Добавляет пира в AmneziaWG напрямую на сервере и в конфигурационный файл"""
        psk_file = None
        max_retries = 3
        sleep_base = 1
        try:
            # Глобальная файл-блокировка, чтобы избежать гонок при параллельных изменениях
            with self._config_lock():
                # внутренняя логика добавления пира
                self._add_peer_internal(
                    public_key, preshared_key, allowed_ip, max_retries, sleep_base
                )
            return
        except Exception as e:
            self.logger.error(
                f"Unexpected error adding peer to awg (outer): {e}", exc_info=True
            )
            try:
                # Попытка сохранить конфиг как fallback под блокировкой
                with self._config_lock():
                    self._save_peer_to_config_file(
                        public_key, preshared_key, allowed_ip
                    )
            except Exception:
                self.logger.exception("Failed to save peer to config file as fallback")
            finally:
                if psk_file and os.path.exists(psk_file):
                    try:
                        os.unlink(psk_file)
                    except Exception:
                        pass

    def _add_peer_internal(
        self,
        public_key: str,
        preshared_key: str,
        allowed_ip: str,
        max_retries: int,
        sleep_base: int,
    ):
        psk_file = None
        try:
            # Проверяем существование пира
            try:
                check_cmd = ["sudo", "awg", "show", config.WG_INTERFACE, "peers"]
                result = subprocess.run(check_cmd, capture_output=True, text=True)
                peer_exists = public_key in (result.stdout or "")
            except Exception as e:
                self.logger.debug(f"Failed to check existing peers: {e}")
                peer_exists = False

            if peer_exists:
                try:
                    subprocess.run(
                        [
                            "sudo",
                            "awg",
                            "set",
                            config.WG_INTERFACE,
                            "peer",
                            public_key,
                            "remove",
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.logger.info(
                        f"Removed existing peer {public_key[:8]}... before re-adding"
                    )
                except Exception as e:
                    self.logger.debug(f"Failed to remove existing peer: {e}")

            # Создаем временный файл для preshared-key
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".psk", delete=False
            ) as f:
                f.write(preshared_key)
                psk_file = f.name

            # Пытаемся добавить пира с retry и проверкой
            added = False
            cmd = [
                "sudo",
                "awg",
                "set",
                config.WG_INTERFACE,
                "peer",
                public_key,
                "preshared-key",
                psk_file,
                "allowed-ips",
                f"{allowed_ip}/32",
            ]

            for attempt in range(1, max_retries + 1):
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True)
                    if proc.returncode == 0:
                        self.logger.info(
                            f"Added peer {public_key[:8]}... to awg with IP {allowed_ip} (attempt {attempt})"
                        )
                        added = True
                        break
                    else:
                        self.logger.warning(
                            f"awg set failed (attempt {attempt}): {proc.stderr.strip()}"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Exception running awg set (attempt {attempt}): {e}"
                    )

                time.sleep(sleep_base * attempt)

            # Если добавление через awg не сработало, всё равно добавляем запись в конфиг сервера
            if not added:
                self.logger.warning(
                    "Adding peer via awg failed after retries — appending to server config"
                )
                self._save_peer_to_config_file(public_key, preshared_key, allowed_ip)

            # Проверяем, что allowed-ips содержит новую запись — если нет, пробуем ещё раз
            try:
                show_cmd = [
                    "sudo",
                    "awg",
                    "show",
                    config.WG_INTERFACE,
                    "allowed-ips",
                ]
                verify = subprocess.run(show_cmd, capture_output=True, text=True)
                out = verify.stdout or ""
                if self._allowed_ip_is_present(out, public_key, allowed_ip):
                    self.logger.info(
                        f"Verified peer present in awg allowed-ips: {public_key[:8]} -> {allowed_ip}"
                    )
                    self._save_peer_to_config_file(
                        public_key, preshared_key, allowed_ip
                    )
                else:
                    # one more attempt to append config and reload
                    self.logger.warning(
                        "Peer not visible in allowed-ips after add — appending and retrying awg set once more"
                    )
                    self._save_peer_to_config_file(
                        public_key, preshared_key, allowed_ip
                    )
                    # try one more awg set
                    try:
                        proc = subprocess.run(cmd, capture_output=True, text=True)
                        if proc.returncode == 0:
                            self.logger.info(
                                "awg set succeeded on retry after appending to config"
                            )
                    except Exception:
                        pass
                    # Final verification after fallback
                    verify2 = subprocess.run(show_cmd, capture_output=True, text=True)
                    out2 = verify2.stdout or ""
                    if self._allowed_ip_is_present(out2, public_key, allowed_ip):
                        self.logger.info(
                            f"Peer visible after fallback append: {public_key[:8]} -> {allowed_ip}"
                        )
                    else:
                        self.logger.error(
                            f"Peer still not visible after fallback: {public_key[:8]} -> {allowed_ip}"
                        )
            except Exception as e:
                self.logger.debug(f"Failed to verify awg allowed-ips: {e}")

        except Exception as e:
            self.logger.error(
                f"Unexpected error adding peer to awg (inner): {e}", exc_info=True
            )
        finally:
            # Удаляем временный файл
            if psk_file and os.path.exists(psk_file):
                try:
                    os.unlink(psk_file)
                except Exception:
                    pass

    @contextlib.contextmanager
    def _config_lock(self):
        """Context manager для файловой блокировки, чтобы избежать гонок при изменении server config"""
        lock_path = "/var/lock/wg_manager.lock"
        fd = None
        try:
            fd = open(lock_path, "w")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                if fd:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    fd.close()
            except Exception:
                pass

    def _save_peer_to_config_file(
        self, public_key: str, preshared_key: str, allowed_ip: str
    ):
        """Сохраняет пира в конфигурационный файл /etc/amnezia/amneziawg/wg0.conf"""
        try:
            server_config_path = self._get_server_config_path()
            # Читаем текущий конфиг через sudo, на случай если бот не root
            try:
                read_proc = subprocess.run(
                    ["sudo", "cat", server_config_path], capture_output=True, text=True
                )
                if read_proc.returncode == 0:
                    config_content = read_proc.stdout
                else:
                    self.logger.warning(
                        f"Unable to read {server_config_path} via sudo: {read_proc.stderr.strip()}"
                    )
                    # Попробуем открыть напрямую
                    with open(server_config_path, "r") as f:
                        config_content = f.read()
            except Exception:
                with open(server_config_path, "r") as f:
                    config_content = f.read()

            # Проверяем, есть ли уже такой пир
            if f"PublicKey = {public_key}" in config_content:
                self.logger.info(
                    f"Peer {public_key[:8]}... already exists in awg config"
                )
                return

            # Добавляем нового пира в конец конфига
            peer_config = f"""
[Peer]
PublicKey = {public_key}
PresharedKey = {preshared_key}
AllowedIPs = {allowed_ip}/32
"""

            # Создаем временный файл с новым содержимым и атомарно заменяем оригинал под sudo
            try:
                timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
                backup_path = f"{server_config_path}.bak.{timestamp}"

                # Подготовим новый файл во временной директории
                tmp = tempfile.NamedTemporaryFile(mode="w", delete=False)
                try:
                    tmp.write(config_content)
                    tmp.write(peer_config)
                    tmp.flush()
                finally:
                    tmp.close()

                # Сделаем резервную копию оригинального файла
                subprocess.run(
                    ["sudo", "cp", server_config_path, backup_path], check=False
                )

                # Переместим временный файл на место конфига под sudo
                mv_cmd = f"mv {tmp.name} {server_config_path} && chown root:root {server_config_path} && chmod 600 {server_config_path}"
                proc = subprocess.run(
                    ["sudo", "bash", "-c", mv_cmd], capture_output=True, text=True
                )
                if proc.returncode == 0:
                    self.logger.info(
                        f"Atomically replaced {server_config_path} and created backup {backup_path}"
                    )
                else:
                    self.logger.error(
                        f"Failed to atomically replace server config: {proc.stderr}"
                    )
                    # Попытка append через tee как fallback
                    proc2 = subprocess.run(
                        ["sudo", "tee", "-a", server_config_path],
                        input=peer_config,
                        text=True,
                        capture_output=True,
                    )
                    if proc2.returncode == 0:
                        self.logger.info(
                            f"Appended peer {public_key[:8]}... to {server_config_path} via tee fallback"
                        )
                    else:
                        self.logger.error(
                            f"Fallback append also failed: {proc2.stderr}"
                        )
            except Exception as e:
                self.logger.error(f"Failed to write to server config atomically: {e}")
                raise

        except Exception as e:
            self.logger.error(f"Error saving peer to config file: {e}")

    def generate_qr(self, config_path: str) -> str:
        """Генерирует QR-код для конфига"""
        try:
            import qrcode

            with open(config_path, "r") as f:
                config_text = f.read()

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(config_text)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            qr_path = config_path.replace(".conf", ".png")
            img.save(qr_path)
            return qr_path
        except ImportError:
            # Если qrcode не установлен, возвращаем путь к конфигу
            return config_path


wg_manager = WireGuardManager()
