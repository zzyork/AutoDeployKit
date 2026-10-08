#!/usr/bin/env bash
set -Eeuo pipefail

# Update this version before preparing each release; the release command embeds the image digest and Compose hash.
WEBUI_VERSION="0.1.2"
WEBUI_IMAGE_DIGEST="__IMAGE_DIGEST__"
WEBUI_COMPOSE_SHA256="__COMPOSE_SHA256__"
PROJECT="autodeploykit"
IMAGE="ghcr.io/zzyork/autodeploykit-webui"
COMPOSE_FILE="compose.webui.yaml"
DEFAULT_DOWNLOAD_BASE="https://github.com/zzyork/AutoDeployKit/releases/download"

fail() { printf '错误：%s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

prepare_release() {
    local root output hash digest
    root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
    docker build -t "$IMAGE:v$WEBUI_VERSION" -f "$root/Dockerfile.webui" "$root"
    docker push "$IMAGE:v$WEBUI_VERSION"
    digest="$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE:v$WEBUI_VERSION")"
    digest="${digest##*@}"
    output="$root/dist/v${WEBUI_VERSION}"
    mkdir -p -- "$output"
    cp -- "$root/$COMPOSE_FILE" "$output/$COMPOSE_FILE"
    hash="$(sha256sum "$output/$COMPOSE_FILE")"
    hash="${hash%% *}"
    sed -e "s/__IMAGE_DIGEST__/$digest/g" -e "s/__COMPOSE_SHA256__/$hash/g" "$root/scripts/install_webui.sh" | tr -d '\r' > "$output/install_webui.sh"
    chmod 755 "$output/install_webui.sh"
    say "发布镜像：$IMAGE@$digest"
    say "部署文件：$output/$COMPOSE_FILE"
    say "发布脚本：$output/install_webui.sh"
    say "Compose SHA-256：$hash"
}

if [[ "${1:-}" == "--prepare-release" ]]; then
    prepare_release
    exit
fi
[[ $# -eq 0 ]] || fail '用法：bash install_webui.sh'
[[ "$WEBUI_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ && "$WEBUI_COMPOSE_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail '该文件是源码模板；请使用发布版本的安装脚本。'
[[ -t 0 && -t 1 ]] || fail '安装及管理员口令初始化必须在交互终端运行。'
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail '首版仅支持 Linux x86_64。'
[[ $EUID -eq 0 ]] || fail '请以 root 身份运行安装脚本。'
for tool in sha256sum mktemp; do command -v "$tool" >/dev/null || fail "系统缺少基础工具 $tool"; done

confirm() {
    local answer
    read -r -p "$1 [y/N] " answer
    [[ "$answer" == [yY] ]]
}

check_curl() {
    command -v curl >/dev/null && return
    confirm 'curl 未安装，是否从系统软件源安装？' || fail '需要 curl 下载部署文件。'
    if command -v apt-get >/dev/null; then
        apt-get update
        apt-get install -y curl
    elif command -v dnf >/dev/null; then
        dnf install -y curl
    else
        fail '仅支持从 APT/DNF 软件源安装 curl。'
    fi
    command -v curl >/dev/null || fail 'curl 安装后仍不可用。'
}

check_docker() {
    if ! command -v docker >/dev/null; then
        confirm 'Docker 未安装，是否从系统软件源安装并启动 Docker？' || fail '需要 Docker Engine。'
        if command -v apt-get >/dev/null; then
            apt-get update
            apt-get install -y docker.io
        elif command -v dnf >/dev/null; then
            dnf install -y docker
        else
            fail '仅支持从 APT/DNF 软件源安装 Docker，请先准备受支持的系统。'
        fi
        systemctl enable --now docker
    fi
    if ! docker info >/dev/null 2>&1; then
        confirm 'Docker 守护进程不可用，是否尝试启动并设置开机启动？' || fail '需要运行中的 Docker 守护进程。'
        systemctl enable --now docker
        docker info >/dev/null || fail '无法访问 Docker 守护进程。'
    fi
    if docker compose version >/dev/null 2>&1; then
        COMPOSE=(docker compose)
    elif command -v docker-compose >/dev/null && docker-compose version --short 2>/dev/null | grep -q '^2\.'; then
        COMPOSE=(docker-compose)
    else
        confirm 'Compose v2 未安装，是否从系统软件源安装？' || fail '需要 Compose v2。'
        if command -v apt-get >/dev/null; then
            apt-get update
            if apt-cache show docker-compose-plugin >/dev/null 2>&1; then
                apt-get install -y docker-compose-plugin
            else
                apt-get install -y docker-compose-v2
            fi
        elif command -v dnf >/dev/null; then
            dnf install -y docker-compose-plugin
        else
            fail '找不到支持的 Compose v2 软件源。'
        fi
        docker compose version >/dev/null || fail 'Compose v2 安装后仍不可用。'
        COMPOSE=(docker compose)
    fi
}

valid_ip() {
    local part
    local -a octets
    [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
    local IFS=.
    read -r -a octets <<< "$1"
    for part in "${octets[@]}"; do
        (( 10#$part <= 255 )) || return 1
    done
    (( 10#${octets[0]} > 0 && 10#${octets[0]} < 224 && 10#${octets[0]} != 127 ))
}

collect_addresses() {
    command -v ip >/dev/null || fail '缺少 ip 命令，无法读取网卡地址。'
    mapfile -t WEBUI_ADDRESSES < <(ip -o -4 addr show scope global | awk '{sub(/\/.*/, "", $4); print $4}' | sort -u)
    ((${#WEBUI_ADDRESSES[@]} > 0)) || fail '没有检测到可用的非回环 IPv4 网卡地址。'
    local address
    for address in "${WEBUI_ADDRESSES[@]}"; do
        valid_ip "$address" || fail '检测到无效的网卡地址。'
    done
    WEBUI_CHECK_IP="${WEBUI_ADDRESSES[0]}"
    WEBUI_TLS_IPS="$(IFS=,; printf '%s' "${WEBUI_ADDRESSES[*]}")"
    export WEBUI_TLS_IPS
}

read_settings() {
    read -r -p '安装目录（默认 /data/autodeploykit）：' INSTALL_DIR
    INSTALL_DIR="${INSTALL_DIR:-/data/autodeploykit}"
    [[ "$INSTALL_DIR" == /* && "$INSTALL_DIR" != / && ! "$INSTALL_DIR" =~ (^|/)\.\.(/|$) && ! -L "$INSTALL_DIR" ]] || fail '安装目录必须为非根目录的绝对路径，不能包含 .. 或符号链接。'
    collect_addresses
    say '将为当前网卡 IPv4 地址生成证书：'
    printf '  %s\n' "${WEBUI_ADDRESSES[@]}"
    read -r -p 'HTTPS 端口（默认 8765）：' WEBUI_PORT
    WEBUI_PORT="${WEBUI_PORT:-8765}"
    [[ "$WEBUI_PORT" =~ ^[0-9]{1,5}$ ]] && (( 10#$WEBUI_PORT >= 1 && 10#$WEBUI_PORT <= 65535 )) || fail '无效端口。'
    WEBUI_PORT="$((10#$WEBUI_PORT))"
    export WEBUI_PORT
}

download_release() {
    local base
    base="${AUTODEPLOYKIT_WEBUI_DOWNLOAD_BASE_URL:-$DEFAULT_DOWNLOAD_BASE}"
    [[ "$base" =~ ^https://[a-zA-Z0-9.-]+(:[0-9]+)?(/[a-zA-Z0-9._/-]*)?$ ]] || fail '下载源必须为不含凭据和参数的 HTTPS 基础地址。'
    base="${base%/}"
    STAGE="$(mktemp -d "$INSTALL_DIR/.install.XXXXXX")"
    curl --proto '=https' --tlsv1.2 -fL --retry 3 --output "$STAGE/$COMPOSE_FILE" "$base/v${WEBUI_VERSION}/$COMPOSE_FILE"
    printf '%s  %s\n' "$WEBUI_COMPOSE_SHA256" "$STAGE/$COMPOSE_FILE" | sha256sum -c - >/dev/null || fail '部署文件 SHA-256 校验失败。'
    RELEASE_DIR="$INSTALL_DIR/releases/v${WEBUI_VERSION}"
    if [[ -e "$RELEASE_DIR" ]]; then
        [[ -f "$RELEASE_DIR/$COMPOSE_FILE" && ! -L "$RELEASE_DIR/$COMPOSE_FILE" ]] || fail '已有同版本目录的部署文件缺失或无效。'
        printf '%s  %s\n' "$WEBUI_COMPOSE_SHA256" "$RELEASE_DIR/$COMPOSE_FILE" | sha256sum -c - >/dev/null || fail '已有同版本部署文件与发布物不匹配，请人工检查。'
        if [[ -e "$RELEASE_DIR/.image-ref" ]]; then
            [[ -f "$RELEASE_DIR/.image-ref" && ! -L "$RELEASE_DIR/.image-ref" && "$(< "$RELEASE_DIR/.image-ref")" == "$IMAGE@$WEBUI_IMAGE_DIGEST" ]] || fail '已有同版本镜像与发布物不匹配，请人工检查。'
        fi
    else
        mkdir -p -- "$INSTALL_DIR/releases" "$STAGE/release"
        mv -- "$STAGE/$COMPOSE_FILE" "$STAGE/release/$COMPOSE_FILE"
        mv -- "$STAGE/release" "$RELEASE_DIR"
    fi
}

compose_at() {
    local directory="$1"
    shift
    "${COMPOSE[@]}" -p "$PROJECT" -f "$directory/compose.webui.yaml" "$@"
}

volume_exists() { docker volume inspect "${PROJECT}_$1" >/dev/null 2>&1; }

check_space() {
    local directory free_kb
    for directory in "$INSTALL_DIR" "$(docker info --format '{{.DockerRootDir}}')"; do
        free_kb="$(df -Pk "$directory" | awk 'NR == 2 {print $4}')"
        [[ "$free_kb" =~ ^[0-9]+$ && "$free_kb" -ge 1048576 ]] || fail "目录 $directory 可用空间不足 1 GiB。"
    done
}

backup_upgrade() {
    local backup_dir
    mkdir -m 700 -p -- "$INSTALL_DIR/backups"
    backup_dir="$(mktemp -d "$INSTALL_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")"
    say "正在备份数据库、报告和密钥至 $backup_dir"
    docker run --rm --user 0 \
        -v "${PROJECT}_webui_data:/data:ro" -v "${PROJECT}_webui_key:/key:ro" \
        -v "$backup_dir:/backup" "$WEBUI_IMAGE" \
        autodeploykit-webui-init --backup-dir /backup --data-dir /data --key-file /key/master.key || return 1
    say "备份完成：$backup_dir"
}

restore_old() {
    WEBUI_IMAGE="${OLD_IMAGE:-$WEBUI_IMAGE}" WEBUI_IMAGE_TAG="$OLD_VERSION" \
        compose_at "$INSTALL_DIR/releases/v$OLD_VERSION" up -d --no-deps webui || true
}

cleanup() { [[ -z "${STAGE:-}" ]] || rm -rf -- "$STAGE"; }
trap cleanup EXIT

read_settings
[[ -d "$INSTALL_DIR" || ! -e "$INSTALL_DIR" ]] || fail '安装路径不是目录。'
mkdir -p -- "$INSTALL_DIR"
check_curl
download_release
check_docker
check_space
collect_addresses
WEBUI_IMAGE="$IMAGE@$WEBUI_IMAGE_DIGEST"
export WEBUI_IMAGE
STATE="$INSTALL_DIR/installation.state"
if [[ -f "$STATE" ]]; then
    IFS='|' read -r OLD_VERSION OLD_IP OLD_PORT < "$STATE"
    [[ "$OLD_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$OLD_PORT" =~ ^[0-9]{1,5}$ ]] && valid_ip "$OLD_IP" || fail '安装状态无效，请人工检查。'
    [[ "$OLD_PORT" == "$WEBUI_PORT" ]] || fail '升级不能同时改变端口；请先保留原设置。'
    [[ -f "$INSTALL_DIR/releases/v$OLD_VERSION/compose.webui.yaml" ]] || fail '原版本部署文件缺失。'
    if [[ -f "$INSTALL_DIR/releases/v$OLD_VERSION/.image-ref" ]]; then
        OLD_IMAGE="$(< "$INSTALL_DIR/releases/v$OLD_VERSION/.image-ref")"
        [[ "$OLD_IMAGE" =~ ^ghcr\.io/zzyork/autodeploykit-webui@sha256:[0-9a-f]{64}$ ]] || fail '原版本镜像引用无效，请人工检查。'
    fi
    volume_exists webui_data && volume_exists webui_key || fail '已有安装缺少数据卷或密钥卷，拒绝初始化。'
    if [[ "$OLD_VERSION" == "$WEBUI_VERSION" ]]; then
        SAME_VERSION=1
        say '已安装当前版本；将检查证书并重新启动服务。'
    else
        confirm "将从 $OLD_VERSION 升级到 $WEBUI_VERSION；服务会短暂中断，是否继续？" || exit 0
    fi
else
    if volume_exists webui_data || volume_exists webui_key; then
        [[ -f "$INSTALL_DIR/.install-pending" ]] && volume_exists webui_data && volume_exists webui_key || fail '发现没有安装记录的 WebUI 数据卷；请先人工确认原部署，避免覆盖。'
    fi
    if [[ ! -f "$INSTALL_DIR/.install-pending" ]] && command -v ss >/dev/null && ss -H -ltn "sport = :$WEBUI_PORT" | grep -q .; then
        fail "端口 $WEBUI_PORT 已被占用。"
    fi
    confirm '将公开监听 HTTPS 端口，且不限制来源 IP；是否继续？' || exit 0
fi

docker pull "$WEBUI_IMAGE" || fail '无法拉取发布镜像；旧服务未被停止。'
if [[ "${SAME_VERSION:-0}" == 1 ]]; then
    compose_at "$RELEASE_DIR" --profile setup run --rm --no-deps init --tls-only
    compose_at "$RELEASE_DIR" up -d --force-recreate --no-deps webui
else
    if [[ -f "$STATE" ]]; then
        WEBUI_IMAGE_TAG="$OLD_VERSION" compose_at "$INSTALL_DIR/releases/v$OLD_VERSION" stop webui
        if ! backup_upgrade; then
            restore_old
            fail '备份失败，已尝试恢复旧服务；未执行升级。'
        fi
        say '备份已保存。若新版本启动失败，不会自动切回可能不兼容的旧数据库。'
        if ! compose_at "$RELEASE_DIR" --profile setup run --rm --no-deps init --tls-only; then
            restore_old
            fail '证书检查失败，已尝试恢复旧服务；未执行升级。'
        fi
    else
        : > "$INSTALL_DIR/.install-pending"
        compose_at "$RELEASE_DIR" --profile setup run --rm --no-deps init
    fi
    compose_at "$RELEASE_DIR" up -d --no-deps webui
fi
before_tls_ips="$WEBUI_TLS_IPS"
collect_addresses
if [[ "$before_tls_ips" != "$WEBUI_TLS_IPS" ]]; then
    compose_at "$RELEASE_DIR" --profile setup run --rm --no-deps init --tls-only
    compose_at "$RELEASE_DIR" up -d --force-recreate --no-deps webui
fi
container="$(compose_at "$RELEASE_DIR" ps -q webui)"
[[ -n "$container" ]] || fail 'WebUI 容器未启动。'
docker cp "$container:/etc/autodeploykit/tls.crt" "$STAGE/tls.crt"
ready=0
for ((attempt=0; attempt<20; attempt++)); do
    if curl -fsS --cacert "$STAGE/tls.crt" --resolve "$WEBUI_CHECK_IP:$WEBUI_PORT:127.0.0.1" "https://$WEBUI_CHECK_IP:$WEBUI_PORT/" -o /dev/null; then
        ready=1
        break
    fi
    sleep 2
done
[[ $ready -eq 1 ]] || fail 'HTTPS 启动检查失败，请检查容器日志；数据卷和备份均已保留。'
fingerprint="$(docker exec "$container" autodeploykit-webui-init --tls-fingerprint)"
printf '%s\n' "$WEBUI_IMAGE" > "$RELEASE_DIR/.image-ref"
printf '%s|%s|%s\n' "$WEBUI_VERSION" "$WEBUI_CHECK_IP" "$WEBUI_PORT" > "$STATE.tmp"
chmod 600 "$STATE.tmp"
mv -- "$STATE.tmp" "$STATE"
rm -f -- "$INSTALL_DIR/.install-pending"
say 'WebUI 已启动，可通过以下网卡地址访问（网络与防火墙须允许）：'
for address in "${WEBUI_ADDRESSES[@]}"; do
    say "https://$address:$WEBUI_PORT/"
done
say "证书 SHA-256 指纹：$fingerprint"
say '自签名证书不会自动受到浏览器信任，首次访问请核对证书后继续。'
