#!/usr/bin/env bash
set -euo pipefail

die() { printf '%s\n' "$*" >&2; exit 2; }

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
COMPOSE="$ROOT/compose.webui.yaml"

compose() { docker compose --project-directory "$ROOT" -f "$COMPOSE" "$@"; }

ensure_docker() {
  local missing_docker=0 missing_compose=0 answer missing endpoint
  local -a privileged=() packages=()
  if ! command -v docker >/dev/null || ! docker --version >/dev/null 2>&1; then
    missing_docker=1
  fi
  if (( missing_docker )) || ! docker compose version >/dev/null 2>&1; then
    missing_compose=1
  fi
  if (( missing_docker || missing_compose )); then
    missing="$(if (( missing_docker )); then printf 'Docker Engine '; fi)$(if (( missing_compose )); then printf 'Docker Compose 插件'; fi)"
    read -r -p "缺少 ${missing}。是否通过本机已配置的软件仓库安装，并在需要时启用 Docker 服务？[y/N] " answer || die '未确认安装，已退出。'
    [[ "$answer" == y || "$answer" == Y ]] || die '已取消安装。'
    if (( EUID != 0 )); then
      command -v sudo >/dev/null || die '安装需要 root 权限或 sudo。'
      privileged=(sudo)
    fi
    if command -v apt-get >/dev/null; then
      "${privileged[@]}" apt-get update
      if (( missing_docker )); then
        if apt-cache show docker-ce containerd.io >/dev/null 2>&1; then
          packages+=(docker-ce docker-ce-cli containerd.io)
        else
          packages+=(docker.io)
        fi
      fi
      if (( missing_compose )); then
        if apt-cache show docker-compose-plugin >/dev/null 2>&1; then
          packages+=(docker-compose-plugin)
        elif apt-cache show docker-compose-v2 >/dev/null 2>&1; then
          packages+=(docker-compose-v2)
        else
          die '当前 APT 仓库没有 Docker Compose v2 插件；请先配置可信软件仓库。'
        fi
      fi
      "${privileged[@]}" apt-get --no-remove install -y "${packages[@]}"
    elif command -v dnf >/dev/null; then
      if (( missing_docker )); then
        packages+=(docker-ce docker-ce-cli containerd.io)
      fi
      if (( missing_compose )); then
        packages+=(docker-compose-plugin)
      fi
      "${privileged[@]}" dnf install -y "${packages[@]}" || die 'DNF 安装失败；请检查 Docker 官方仓库是否已配置。'
    else
      die '只支持从已配置的 APT 或 DNF 仓库安装；请自行安装 Docker Engine 和 Compose 插件。'
    fi
    if (( missing_docker )); then
      command -v systemctl >/dev/null || die 'Docker 已安装，但没有 systemctl；请自行启动 Docker 服务。'
      "${privileged[@]}" systemctl enable --now docker
    fi
  fi
  command -v docker >/dev/null && docker compose version >/dev/null 2>&1 || die 'Docker Engine 或 Compose 插件仍不可用。'
  endpoint="$(docker context inspect "$(docker context show)" --format '{{(index .Endpoints "docker").Host}}')" || die '无法检查 Docker context。'
  [[ "$endpoint" == unix:///* && ( -z "${DOCKER_HOST:-}" || "$DOCKER_HOST" == unix:///* ) ]] || die '当前 Docker context 或 DOCKER_HOST 指向非本机 Unix socket，拒绝部署。'
  docker info >/dev/null 2>&1 || die '无法访问 Docker 守护进程；请检查服务状态或当前用户权限。'
}

main() {
  local mode="${1:-install}"
  [[ $# -le 1 && ( "$mode" == install || "$mode" == upgrade ) ]] || die '用法：bash scripts/install_webui.sh [install|upgrade]'
  [[ -f "$COMPOSE" && -f "$ROOT/Dockerfile.webui" && -f "$ROOT/pyproject.toml" ]] || die '请从包含完整源码和 Compose 配置的交付目录运行。'
  [[ ! -e /etc/systemd/system/autodeploykit-webui.service ]] || die '检测到旧 systemd 安装；请人工备份和迁移，不要同时启动两个服务。'
  [[ "$mode" != install || -t 0 ]] || die '首次安装必须在交互终端设置管理员口令。'
  ensure_docker

  compose build webui
  if [[ "$mode" == upgrade ]]; then
    compose --profile setup run --rm --no-deps --entrypoint /bin/sh init -c \
      'test -f /var/lib/autodeploykit/webui.sqlite3 && test -s /etc/autodeploykit/master.key' \
      || die '数据库或根密钥缺失，拒绝升级；请先检查和恢复备份。'
  else
    compose --profile setup run --rm --no-deps --entrypoint /bin/sh init -c \
      'test ! -e /var/lib/autodeploykit/webui.sqlite3 && test ! -e /etc/autodeploykit/master.key' \
      || die '发现已有数据或密钥，拒绝重复安装；升级请使用 upgrade。'
  fi

  compose --profile setup run --rm --no-deps init
  compose up -d --no-deps webui
  compose ps webui
  printf 'WebUI 已通过容器%s；访问地址：http://127.0.0.1:8765（请配置 HTTPS 反向代理）。\n' "$([[ "$mode" == install ]] && printf '安装' || printf '升级')"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
