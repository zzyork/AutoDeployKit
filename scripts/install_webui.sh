#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${WEBUI_INSTALL_DIR:-/opt/autodeploykit}"
DATA_DIR="${WEBUI_DATA_DIR:-/var/lib/autodeploykit}"
CONFIG_DIR="${WEBUI_CONFIG_DIR:-/etc/autodeploykit}"
USER_NAME="autodeploykit"
UNIT="/etc/systemd/system/autodeploykit-webui.service"
WHEEL="${1:-}"

if [[ "$(id -u)" -ne 0 || -z "$WHEEL" || ! -f "$WHEEL" ]]; then
  printf '用法：以 root 在本机运行 %s /absolute/path/autodeploykit.whl\n' "$0" >&2
  exit 2
fi
for directory in "$INSTALL_DIR" "$DATA_DIR" "$CONFIG_DIR"; do
  if [[ "$directory" != /* || "$directory" == / || -L "$directory" || "$directory" =~ [[:space:]] ]]; then
    printf '安装目录必须是安全的绝对路径：%s\n' "$directory" >&2
    exit 2
  fi
done
if [[ "$INSTALL_DIR" == "$DATA_DIR" || "$INSTALL_DIR" == "$CONFIG_DIR" || "$DATA_DIR" == "$CONFIG_DIR" ||
      "$DATA_DIR" == "$INSTALL_DIR"/* || "$CONFIG_DIR" == "$INSTALL_DIR"/* ||
      "$INSTALL_DIR" == "$DATA_DIR"/* || "$INSTALL_DIR" == "$CONFIG_DIR"/* ||
      "$CONFIG_DIR" == "$DATA_DIR"/* || "$DATA_DIR" == "$CONFIG_DIR"/* ]]; then
  printf '安装、数据和配置目录必须分开。\n' >&2
  exit 2
fi
KEY_FILE="$CONFIG_DIR/master.key"
ENV_FILE="$CONFIG_DIR/webui.env"
if [[ -L "$UNIT" || -L "$ENV_FILE" || -L "$KEY_FILE" ]]; then
  printf '服务配置、环境配置和加密根密钥不能是符号链接。\n' >&2
  exit 2
fi
if [[ -e "$ENV_FILE" ]] &&
   { ! grep -Fxq "WEBUI_DATA_DIR=$DATA_DIR" "$ENV_FILE" || ! grep -Fxq "WEBUI_KEY_FILE=$KEY_FILE" "$ENV_FILE"; }; then
  printf '现有环境配置与请求的目录不同，请先检查配置。\n' >&2
  exit 2
fi
if [[ -e "$UNIT" ]] &&
   { ! grep -Fxq "ExecStart=$INSTALL_DIR/.venv/bin/python -m uvicorn webui.app:create_app --factory --host 127.0.0.1 --port 8765 --workers 1" "$UNIT" ||
     ! grep -Fxq "EnvironmentFile=$ENV_FILE" "$UNIT"; }; then
  printf '现有服务配置与交付包不一致，拒绝自动覆盖或重启。\n' >&2
  exit 2
fi
for command in python3.14 systemctl runuser useradd; do
  command -v "$command" >/dev/null || { printf '缺少命令：%s\n' "$command" >&2; exit 2; }
done
python3.14 -m pip --version >/dev/null
if [[ -e "$UNIT" ]]; then
  if [[ ! -t 0 ]]; then
    printf '升级安装必须在本机终端确认。\n' >&2
    exit 2
  fi
  read -r -p '检测到已有服务，确认更新软件并重启服务？[y/N] ' answer
  [[ "$answer" == y || "$answer" == Y ]] || exit 0
elif [[ ! -t 0 && ! -f "$DATA_DIR/webui.sqlite3" ]]; then
  printf '首次安装必须在本机终端设置管理员口令。\n' >&2
  exit 2
fi

if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$USER_NAME"
fi
install -d -m 0750 -o root -g "$USER_NAME" "$INSTALL_DIR" "$CONFIG_DIR"
install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" "$DATA_DIR" "$DATA_DIR/reports"
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  python3.14 -m venv "$INSTALL_DIR/.venv"
fi
case "$("$INSTALL_DIR/.venv/bin/python" --version)" in
  'Python 3.14.'*) ;;
  *) printf '安装目录已有非 Python 3.14 的虚拟环境。\n' >&2; exit 2 ;;
esac
"$INSTALL_DIR/.venv/bin/python" -m pip install --no-input --only-binary=:all: "${WHEEL}[web]"

"$INSTALL_DIR/.venv/bin/python" -m webui.bootstrap --data-dir "$DATA_DIR" --key-file "$KEY_FILE" --create-key-only
chown root:"$USER_NAME" "$KEY_FILE"
chmod 0640 "$KEY_FILE"
runuser -u "$USER_NAME" -- "$INSTALL_DIR/.venv/bin/python" -m webui.bootstrap --data-dir "$DATA_DIR" --key-file "$KEY_FILE"
"$INSTALL_DIR/.venv/bin/python" -m webui.bootstrap --write-instructions "$INSTALL_DIR"
chown root:"$USER_NAME" "$INSTALL_DIR/AGENTS.md" "$INSTALL_DIR/CLAUDE.md"
chmod 0640 "$INSTALL_DIR/AGENTS.md" "$INSTALL_DIR/CLAUDE.md"

if [[ ! -e "$ENV_FILE" ]]; then
  printf 'WEBUI_DATA_DIR=%s\nWEBUI_KEY_FILE=%s\n' "$DATA_DIR" "$KEY_FILE" > "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  chown root:"$USER_NAME" "$ENV_FILE"
fi

if [[ ! -e "$UNIT" ]]; then
  cat > "$UNIT" <<EOF
[Unit]
Description=AutoDeployKit WebUI
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/.venv/bin/python -m uvicorn webui.app:create_app --factory --host 127.0.0.1 --port 8765 --workers 1
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF
  chmod 0644 "$UNIT"
  systemctl daemon-reload
  systemctl enable --now autodeploykit-webui.service
else
  systemctl restart autodeploykit-webui.service
fi
printf 'WebUI 已安装。请在同机反向代理启用 HTTPS 和内网访问限制。\n'
