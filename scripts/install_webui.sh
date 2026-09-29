#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${WEBUI_INSTALL_DIR:-/opt/autodeploykit}"
DATA_DIR="${WEBUI_DATA_DIR:-/var/lib/autodeploykit}"
CONFIG_DIR="${WEBUI_CONFIG_DIR:-/etc/autodeploykit}"
USER_NAME="autodeploykit"
UNIT="/etc/systemd/system/autodeploykit-webui.service"
ENV_FILE="$CONFIG_DIR/webui.env"
KEY_FILE="$CONFIG_DIR/master.key"
PYTHON_DIR="$INSTALL_DIR/python-3.14"
VENV="$INSTALL_DIR/.venv"
NEXT_VENV="$INSTALL_DIR/.venv-next"
OLD_VENV="$INSTALL_DIR/.venv-old"

die() { printf '%s\n' "$*" >&2; exit 2; }

check_layout() {
  local directory other
  for directory in "$INSTALL_DIR" "$DATA_DIR" "$CONFIG_DIR"; do
    [[ "$directory" =~ ^/[A-Za-z0-9_./-]+$ && "$directory" != / ]] || die "目录必须是安全的绝对路径：$directory"
    [[ "$(realpath -m -- "$directory")" == "$directory" ]] || die "目录不能含符号链接或非规范路径：$directory"
    for other in "$INSTALL_DIR" "$DATA_DIR" "$CONFIG_DIR"; do
      if [[ "$directory" != "$other" && "$directory" == "$other"/* ]]; then
        die '安装、数据和配置目录不能相互嵌套。'
      fi
    done
  done
  [[ "$INSTALL_DIR" != "$DATA_DIR" && "$INSTALL_DIR" != "$CONFIG_DIR" && "$DATA_DIR" != "$CONFIG_DIR" ]] || die '安装、数据和配置目录必须分开。'
  for directory in "$UNIT" "$ENV_FILE" "$KEY_FILE" "$VENV" "$NEXT_VENV" "$OLD_VENV" "$PYTHON_DIR" "$INSTALL_DIR/AGENTS.md" "$INSTALL_DIR/CLAUDE.md"; do
    [[ ! -L "$directory" ]] || die "拒绝符号链接：$directory"
  done
}

render_unit() {
  cat <<EOF
[Unit]
Description=AutoDeployKit WebUI
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python -m uvicorn webui.app:create_app --factory --host 127.0.0.1 --port 8765 --workers 1
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF
}

check_existing_install() {
  [[ -f "$UNIT" && -f "$ENV_FILE" ]] || die '未找到完整的 WebUI 服务配置；请检查现有安装。'
  if ! cmp -s "$UNIT" <(render_unit); then
    diff -u "$UNIT" <(render_unit) >&2 || true
    die '现有服务配置与脚本不一致，拒绝自动操作。'
  fi
  printf 'WEBUI_DATA_DIR=%s\nWEBUI_KEY_FILE=%s\n' "$DATA_DIR" "$KEY_FILE" | cmp -s - "$ENV_FILE" || die '现有环境配置与请求的目录不同。'
  if command -v systemctl >/dev/null; then
    [[ "$(systemctl show --property=FragmentPath --value autodeploykit-webui.service)" == "$UNIT" ]] || die 'systemd 加载的服务配置与当前文件不一致。'
    [[ -z "$(systemctl show --property=DropInPaths --value autodeploykit-webui.service)" ]] || die '服务存在 drop-in 覆盖，请先人工检查。'
  fi
}

ask_wheel() {
  local wheel="${1:-}"
  [[ -n "$wheel" ]] || read -r -p '本地 WebUI wheel 的绝对路径：' wheel
  [[ "$wheel" == /* && "$wheel" == *.whl && -f "$wheel" && ! -L "$wheel" ]] || die '需要一个本地 wheel 文件的绝对路径。'
  WHEEL="$wheel"
}

python_ready() {
  local python="$1"
  [[ -x "$python" || "${python##*/}" == "$python" && -n "$(command -v "$python" || true)" ]] || return 1
  [[ "$("$python" --version 2>/dev/null)" == Python\ 3.14.* ]] || return 1
  "$python" -m venv --help >/dev/null 2>&1 && "$python" -m ssl >/dev/null 2>&1 && "$python" -m sqlite3 --help >/dev/null 2>&1
}

verify_python_archive() {
  local archive="$1" expected="$2" actual
  [[ "$archive" == /* && -f "$archive" && ! -L "$archive" ]] || die '需要本地官方源码 tar.gz 的绝对路径。'
  [[ "${archive##*/}" =~ ^Python-(3\.14\.[0-9]+)\.tar\.gz$ ]] || die '仅接受 Python-3.14.x.tar.gz 官方源码包。'
  local version="${BASH_REMATCH[1]}"
  [[ "$expected" =~ ^[[:xdigit:]]{64}$ ]] || die 'SHA256 必须为 64 位十六进制值。'
  actual="$(sha256sum -- "$archive")"
  actual="${actual%% *}"
  [[ "$actual" == "${expected,,}" ]] || die 'Python 源码包 SHA256 不匹配。'
  printf '%s\n' "$version"
}

build_python() (
  local archive expected version build_dir="" owned=0
  for program in gcc make tar sha256sum; do
    command -v "$program" >/dev/null || die "缺少源码编译工具：$program"
  done
  read -r -p '官方 Python 3.14 源码 tar.gz 的绝对路径：' archive
  read -r -p '从 python.org 独立核对的 SHA256：' expected
  version="$(verify_python_archive "$archive" "$expected")"
  if [[ -f "$PYTHON_DIR/.autodeploykit-building" ]]; then
    rm -rf -- "$PYTHON_DIR"
  fi
  [[ ! -e "$PYTHON_DIR" ]] || die "已有 Python 目录，拒绝覆盖：$PYTHON_DIR"
  trap 'if [[ "$owned" == 1 ]]; then rm -rf -- "$PYTHON_DIR"; fi; if [[ -n "$build_dir" ]]; then rm -rf -- "$build_dir"; fi' EXIT
  build_dir="$(mktemp -d "$INSTALL_DIR/.python-build.XXXXXX")"
  owned=1
  mkdir -m 0755 "$PYTHON_DIR"
  touch "$PYTHON_DIR/.autodeploykit-building"
  tar -xzf "$archive" -C "$build_dir" --no-same-owner
  [[ -f "$build_dir/Python-$version/configure" ]] || die '源码包缺少 configure。'
  cd "$build_dir/Python-$version"
  ./configure --prefix="$PYTHON_DIR" --with-ensurepip=install
  make -j2
  make altinstall
  "$PYTHON_DIR/bin/python3.14" -m pip --version >/dev/null
  "$PYTHON_DIR/bin/python3.14" -m ssl >/dev/null
  "$PYTHON_DIR/bin/python3.14" -m sqlite3 --help >/dev/null
  touch "$PYTHON_DIR/.autodeploykit-built"
  rm -f -- "$PYTHON_DIR/.autodeploykit-building"
  owned=0
  printf 'Python %s 已安装到 %s（未替换系统 Python）。\n' "$version" "$PYTHON_DIR"
)

ensure_venv() {
  local python created=0
  if [[ -e "$VENV" ]]; then
    python_ready "$VENV/bin/python" || die '现有虚拟环境不是可用的 Python 3.14，拒绝覆盖。'
  else
    if python_ready "$PYTHON_DIR/bin/python3.14"; then
      python="$PYTHON_DIR/bin/python3.14"
    elif python_ready python3.14; then
      python=python3.14
    else
      printf '未检测到可用的 Python 3.14，将使用官方源码包编译。\n'
      build_python
      python="$PYTHON_DIR/bin/python3.14"
    fi
    if ! "$python" -m venv "$VENV"; then
      rm -rf -- "$VENV"
      die '无法建立 Python 3.14 虚拟环境。'
    fi
    created=1
  fi
  if ! "$VENV/bin/python" -m pip --version >/dev/null; then
    [[ "$created" == 0 ]] || rm -rf -- "$VENV"
    die '虚拟环境中缺少 pip；检查 Python 的 ensurepip/venv 支持。'
  fi
}

service_ready() {
  local attempt status main_pid
  sleep 2
  for attempt in {1..30}; do
    if systemctl is-active --quiet autodeploykit-webui.service; then
      main_pid="$(systemctl show --property=MainPID --value autodeploykit-webui.service)" || main_pid=""
      if [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] && (
        exec 3<>/dev/tcp/127.0.0.1/8765
        printf 'GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n' >&3
        IFS= read -r -t 2 status <&3
        [[ "$status" == *" 200 "* ]]
      ) 2>/dev/null && ss -H -ltnp '( sport = :8765 )' | grep -Fq "pid=$main_pid,"; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

fix_entrypoints() {
  local script first
  for script in "$VENV/bin/"*; do
    [[ -f "$script" && -x "$script" && ! -L "$script" ]] || continue
    IFS= read -r first < "$script" || continue
    if [[ "$first" == "#!$NEXT_VENV/bin/python"* ]]; then
      sed -i "1s|^#!.*|#!$VENV/bin/python|" "$script" || return 1
    elif [[ "$first" == '#!/bin/sh' ]] && grep -Fq "$NEXT_VENV/bin/python" "$script"; then
      sed -i "s|$NEXT_VENV/bin/python|$VENV/bin/python|g" "$script" || return 1
    fi
  done
}

install_or_upgrade() {
  local mode="$1" target_venv="$VENV"
  check_layout
  if [[ "$mode" == upgrade ]]; then
    check_existing_install
    [[ -f "$KEY_FILE" ]] || die '加密根密钥丢失，拒绝升级。'
    [[ -f "$DATA_DIR/webui.sqlite3" ]] || die '数据库丢失，拒绝升级。'
    [[ -x "$VENV/bin/python" ]] || die '虚拟环境缺失，拒绝升级。'
    python_ready "$VENV/bin/python" || die '现有虚拟环境不可用，拒绝升级。'
    [[ ! -e "$NEXT_VENV" && ! -e "$OLD_VENV" ]] || die '发现上次升级残留，请先检查虚拟环境。'
  else
    [[ ! -e "$UNIT" && ! -e "$ENV_FILE" ]] || die '检测到已有配置；请选择升级或先检查安装状态。'
  fi
  ask_wheel "${2:-}"
  for program in systemctl runuser useradd ss sed; do
    command -v "$program" >/dev/null || die "缺少命令：$program"
  done
  [[ -d /run/systemd/system ]] || die '目标系统未运行 systemd。'
  if [[ "$mode" == install && ! -f "$DATA_DIR/webui.sqlite3" && ! -t 0 ]]; then
    die '首次安装必须在本机终端设置管理员口令。'
  fi
  if [[ -f "$DATA_DIR/webui.sqlite3" && ! -f "$KEY_FILE" ]]; then
    die '数据库存在但加密根密钥丢失，拒绝重新生成。'
  fi
  if ! id "$USER_NAME" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$USER_NAME"
  fi
  install -d -m 0750 -o root -g "$USER_NAME" "$INSTALL_DIR" "$CONFIG_DIR"
  install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" "$DATA_DIR" "$DATA_DIR/reports"
  if [[ "$mode" == upgrade ]]; then
    if ! "$VENV/bin/python" -m venv "$NEXT_VENV"; then
      rm -rf -- "$NEXT_VENV"
      die '准备新虚拟环境失败，旧服务未更改。'
    fi
    target_venv="$NEXT_VENV"
  else
    ensure_venv
  fi
  if ! "$target_venv/bin/python" -m pip install --no-input --only-binary=:all: --upgrade "${WHEEL}[web]"; then
    [[ "$mode" != upgrade ]] || rm -rf -- "$NEXT_VENV"
    die 'wheel 或依赖安装失败，服务未切换。'
  fi
  if ! "$target_venv/bin/python" -m webui.bootstrap --data-dir "$DATA_DIR" --key-file "$KEY_FILE" --create-key-only; then
    [[ "$mode" != upgrade ]] || rm -rf -- "$NEXT_VENV"
    die '数据库或加密根密钥校验失败，服务未切换。'
  fi
  if ! runuser -u "$USER_NAME" -- "$target_venv/bin/python" -m pip --version >/dev/null; then
    [[ "$mode" != upgrade ]] || rm -rf -- "$NEXT_VENV"
    die '服务账号无法运行新虚拟环境，服务未切换。'
  fi
  chown root:"$USER_NAME" "$KEY_FILE"
  chmod 0640 "$KEY_FILE"
  if [[ "$mode" == install ]]; then
    runuser -u "$USER_NAME" -- "$target_venv/bin/python" -m webui.bootstrap --data-dir "$DATA_DIR" --key-file "$KEY_FILE"
  fi
  for name in AGENTS.md CLAUDE.md; do
    [[ ! -L "$INSTALL_DIR/$name" ]] || die "拒绝符号链接：$INSTALL_DIR/$name"
  done
  "$target_venv/bin/python" -m webui.bootstrap --write-instructions "$INSTALL_DIR"
  chown root:"$USER_NAME" "$INSTALL_DIR/AGENTS.md" "$INSTALL_DIR/CLAUDE.md"
  chmod 0640 "$INSTALL_DIR/AGENTS.md" "$INSTALL_DIR/CLAUDE.md"

  if [[ "$mode" == install ]]; then
    printf 'WEBUI_DATA_DIR=%s\nWEBUI_KEY_FILE=%s\n' "$DATA_DIR" "$KEY_FILE" > "$ENV_FILE"
    chown root:"$USER_NAME" "$ENV_FILE"
    chmod 0640 "$ENV_FILE"
    render_unit > "$UNIT"
    chmod 0644 "$UNIT"
    systemctl daemon-reload
    systemctl enable --now autodeploykit-webui.service
    service_ready || die '服务未就绪，请查看 systemctl status autodeploykit-webui.service。'
  else
    if ! systemctl stop autodeploykit-webui.service; then
      rm -rf -- "$NEXT_VENV"
      die '无法停用旧服务，未切换虚拟环境。'
    fi
    if ! mv -- "$VENV" "$OLD_VENV"; then
      rm -rf -- "$NEXT_VENV"
      systemctl start autodeploykit-webui.service || true
      die '无法保存旧虚拟环境，已尝试恢复旧服务。'
    fi
    if ! mv -- "$NEXT_VENV" "$VENV"; then
      mv -- "$OLD_VENV" "$VENV"
      systemctl start autodeploykit-webui.service
      die '无法切换虚拟环境，已尝试恢复旧服务。'
    fi
    if ! fix_entrypoints || ! systemctl start autodeploykit-webui.service || ! service_ready; then
      systemctl stop autodeploykit-webui.service || die '新服务无法停止；旧虚拟环境仍保留，请人工检查。'
      rm -rf -- "$VENV"
      mv -- "$OLD_VENV" "$VENV"
      systemctl start autodeploykit-webui.service || die '旧服务重启失败，请检查 systemd 日志。'
      service_ready || die '旧服务未就绪，请检查 systemd 日志。'
      die '新版本未就绪，已恢复旧版本。'
    fi
    rm -rf -- "$OLD_VENV"
  fi
  printf 'WebUI 已%s；服务仅监听 127.0.0.1:8765，请配置 HTTPS 反向代理。\n' "$(if [[ "$mode" == install ]]; then printf '安装'; else printf '升级'; fi)"
}

uninstall_webui() {
  local answer
  check_layout
  check_existing_install
  read -r -p '输入 UNINSTALL 确认卸载服务和程序（保留数据库、报告和根密钥）：' answer
  [[ "$answer" == UNINSTALL ]] || { printf '已取消。\n'; return; }
  systemctl disable --now autodeploykit-webui.service
  rm -f -- "$UNIT" "$ENV_FILE"
  systemctl daemon-reload
  rm -rf -- "$VENV" "$NEXT_VENV" "$OLD_VENV"
  if [[ -f "$PYTHON_DIR/.autodeploykit-built" ]]; then
    rm -rf -- "$PYTHON_DIR"
  fi
  printf '服务和程序已卸载；%s、%s 和服务账号仍保留。\n' "$DATA_DIR" "$KEY_FILE"
}

main() {
  local choice
  [[ "$(id -u)" -eq 0 ]] || die '请在目标 Linux 主机的本机终端以 root 执行。'
  command -v realpath >/dev/null || die '缺少 realpath。'
  [[ -t 0 ]] || die '请在本机交互终端运行。'
  while true; do
    printf '\nAutoDeployKit WebUI\n  1) 安装\n  2) 升级\n  3) 卸载（保留数据和密钥）\n  0) 退出\n'
    read -r -p '请选择操作：' choice
    case "$choice" in
      1) install_or_upgrade install "${1:-}"; return ;;
      2) install_or_upgrade upgrade "${1:-}"; return ;;
      3) uninstall_webui; return ;;
      0) return ;;
      *) printf '无效选项。\n' ;;
    esac
  done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
