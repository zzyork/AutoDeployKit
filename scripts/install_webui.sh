#!/usr/bin/env bash

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "Docker 未安装，是否安装 Docker？(y/n)"
        read -r response
        if [[ $response == "y" ]]; then
            curl -fsSL https://get.docker.com -o get-docker.sh
            sh get-docker.sh
        else
            exit 1
        fi
    fi
}

check_docker_compose() {
    if ! command -v docker-compose &> /dev/null; then
        echo "Docker Compose 未安装，是否安装 Docker Compose？(y/n)"
        read -r response
        if [[ $response == "y" ]]; then
            sudo curl -L "https://github.com/docker/compose/releases/download/v2.0.0/docker-compose-linux-x86_64" -o /usr/local/bin/docker-compose
            sudo chmod +x /usr/local/bin/docker-compose
        else
            exit 1
        fi
    fi
}

check_data_directory() {
    local install_dir
    read -r -p "请输入安装目录（默认 /data/autodeploykit）：" install_dir || return 1
    install_dir="${install_dir:-/data/autodeploykit}"
    if [[ "$install_dir" != /* || "$install_dir" == / ]]; then
        echo "安装目录必须是非根目录的绝对路径。" >&2
        return 1
    fi
    if [ ! -d "$install_dir" ]; then
        sudo mkdir -p -- "$install_dir" || return 1
    fi
}
