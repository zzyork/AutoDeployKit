#!/usr/bin/env bash

set -u

CPU_WARNING=80
CPU_CRITICAL=95
MEM_WARNING=80
MEM_CRITICAL=95
DISK_WARNING=80
DISK_CRITICAL=90
SWAP_WARNING=50
SWAP_CRITICAL=80
LOG_DAYS=30
LOG_LINES=200
REPORT_ROOT="server_check/reporters"
GROUP="offline"

LOG_PATHS=(
  "/var/log/messages"
  "/var/log/secure"
  "/var/log/nginx/error.log"
  "/var/log/mysql/error.log"
  "/var/log/mysqld.log"
  "/var/log/rabbitmq/rabbitmqd-error.log"
)

SERVICES=(
  "sshd:sshd"
  "crond:crond"
  "chronyd:chronyd"
  "firewalld:firewalld"
  "NetworkManager:NetworkManager"
  "nginx:nginx"
  "mysqld:mysqld"
  "redis:redis"
  "rabbitmq:rabbitmqd,rabbitmq-server,rabbitmq"
  "docker:docker,dockerd"
  "minio:minio"
  "supervisord:supervisord"
  "prometheus:prometheus"
  "node-exporter:node-exporter"
  "mysqld-exporter:mysqld-exporter"
  "keepalived:keepalived"
  "DmServiceDMSERVER:DmServiceDMSERVER"
)

ALERTS=()
BODY_FILE=""
REPORT_FILE=""

usage() {
  cat <<'EOF'
用法：bash scripts/server_check_offline.sh [选项]

在无法通过 SSH 连接的服务器本机执行巡检，并生成 Markdown 报告。

选项：
  -o, --output DIR      报告根目录，默认 server_check/reporters
  -g, --group NAME      报告分组目录，默认 offline
  --log-days DAYS       journalctl 查询最近天数，默认 30
  --log-lines LINES     每类日志最多保留行数，默认 200
  -h, --help            显示帮助

示例：
  bash scripts/server_check_offline.sh
  bash scripts/server_check_offline.sh -o /tmp/reports -g prod
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)
      REPORT_ROOT="${2:-}"
      shift 2
      ;;
    -g|--group)
      GROUP="${2:-}"
      shift 2
      ;;
    --log-days)
      LOG_DAYS="${2:-}"
      shift 2
      ;;
    --log-lines)
      LOG_LINES="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数：$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

append_body() {
  cat >> "$BODY_FILE"
}

add_alert() {
  ALERTS+=("$1")
}

safe_cmd() {
  local fallback="$1"
  shift
  "$@" 2>/dev/null || printf '%s\n' "$fallback"
}

percent_number() {
  printf '%s' "$1" | grep -Eo '[0-9]+(\.[0-9]+)?' | head -1
}

mark_usage() {
  local value="$1"
  local warning="$2"
  local critical="$3"
  local number
  number="$(percent_number "$value")"
  if [[ -z "$number" ]]; then
    printf ''
  elif awk -v v="$number" -v c="$critical" 'BEGIN { exit !(v >= c) }'; then
    printf ' 🔴 CRITICAL'
  elif awk -v v="$number" -v w="$warning" 'BEGIN { exit !(v >= w) }'; then
    printf ' ⚠️ WARNING'
  else
    printf ' ✅ OK'
  fi
}

is_warning_usage() {
  local value="$1"
  local warning="$2"
  local number
  number="$(percent_number "$value")"
  [[ -n "$number" ]] && awk -v v="$number" -v w="$warning" 'BEGIN { exit !(v >= w) }'
}

is_critical_usage() {
  local value="$1"
  local critical="$2"
  local number
  number="$(percent_number "$value")"
  [[ -n "$number" ]] && awk -v v="$number" -v c="$critical" 'BEGIN { exit !(v >= c) }'
}

collect_server_info() {
  local hostname ipaddress os_name kernel_version uptime_text
  hostname="$(safe_cmd '未知' hostname)"
  ipaddress="$(ip -o -4 addr 2>/dev/null | awk '!/docker|veth|br-|cni|flannel|kube/ && $2!="lo" {print $4}' | uniq)"
  os_name="$(grep PRETTY_NAME /etc/*release 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')"
  kernel_version="$(safe_cmd '未知' uname -r)"
  uptime_text="$(uptime -p 2>/dev/null || uptime 2>/dev/null || echo '未知')"

  append_body <<EOF
## 一、系统基础信息

- **主机名：** \`${hostname}\`

- **IP 地址：**

\`\`\`text
${ipaddress:-无}
\`\`\`

- **操作系统：** \`${os_name:-未知}\`
- **内核版本：** \`${kernel_version}\`
- **运行时长：** \`${uptime_text}\`

---

EOF
}

collect_system_resources() {
  local system_load cpu_usage mem_usage swap_usage cpu_mark mem_mark swap_mark top_cpu top_mem disks_usage
  system_load="$(awk '{print $1,$2,$3}' /proc/loadavg 2>/dev/null || echo '未知')"
  cpu_usage="$(vmstat 1 2 2>/dev/null | tail -1 | awk '{print 100-$15"%"}')"
  [[ -z "$cpu_usage" ]] && cpu_usage="未知"
  mem_usage="$(free -m 2>/dev/null | awk '/Mem:/ {printf "%.1f%%\n", $3/$2*100}')"
  [[ -z "$mem_usage" ]] && mem_usage="未知"
  swap_usage="$(free -m 2>/dev/null | awk '/Swap:/ {if ($2==0) print "0.0%"; else printf "%.1f%%\n", $3/$2*100}')"
  [[ -z "$swap_usage" ]] && swap_usage="未知"
  cpu_mark="$(mark_usage "$cpu_usage" "$CPU_WARNING" "$CPU_CRITICAL")"
  mem_mark="$(mark_usage "$mem_usage" "$MEM_WARNING" "$MEM_CRITICAL")"
  swap_mark="$(mark_usage "$swap_usage" "$SWAP_WARNING" "$SWAP_CRITICAL")"
  top_cpu="$(ps aux --sort=-%cpu 2>/dev/null | head -11 | awk '{cmd=""; for(i=11;i<=NF;i++) cmd=cmd" "$i; printf "%-10s %-6s %-6s %s\n", $1, $3, $4, cmd}')"
  top_mem="$(ps aux --sort=-%mem 2>/dev/null | head -11 | awk '{cmd=""; for(i=11;i<=NF;i++) cmd=cmd" "$i; printf "%-10s %-6s %-6s %s\n", $1, $3, $4, cmd}')"
  disks_usage="$(df -hT 2>/dev/null | awk '$2 ~ /^(ext4|xfs)$/ || NR==1 {print $7,$3,$4,$5,$6}')"

  if is_critical_usage "$cpu_usage" "$CPU_CRITICAL"; then
    add_alert "🔴 **CPU 使用率：** ${cpu_usage}"
  elif is_warning_usage "$cpu_usage" "$CPU_WARNING"; then
    add_alert "⚠️ **CPU 使用率：** ${cpu_usage}"
  fi
  if is_critical_usage "$mem_usage" "$MEM_CRITICAL"; then
    add_alert "🔴 **内存使用率：** ${mem_usage}"
  elif is_warning_usage "$mem_usage" "$MEM_WARNING"; then
    add_alert "⚠️ **内存使用率：** ${mem_usage}"
  fi
  if is_critical_usage "$swap_usage" "$SWAP_CRITICAL"; then
    add_alert "🔴 **Swap 使用率：** ${swap_usage}"
  elif is_warning_usage "$swap_usage" "$SWAP_WARNING"; then
    add_alert "⚠️ **Swap 使用率：** ${swap_usage}"
  fi

  append_body <<EOF
## 二、系统资源与性能

- **系统负载：** \`${system_load}\`
- **CPU 使用率：** \`${cpu_usage}\`${cpu_mark}
- **内存使用率：** \`${mem_usage}\`${mem_mark}
- **Swap 使用率：** \`${swap_usage}\`${swap_mark}

### CPU 使用率 TOP10 进程

\`\`\`text
${top_cpu:-无}
\`\`\`

### 内存使用率 TOP10 进程

\`\`\`text
${top_mem:-无}
\`\`\`

### 磁盘使用率

| 挂载点 | 容量 | 已用 | 可用 | 使用率 |
| --- | --- | --- | --- | --- |
EOF

  while read -r mount size used avail use_percent; do
    [[ -z "${mount:-}" || "$mount" == "Mounted" || "$mount" == "挂载点" ]] && continue
    local disk_mark=""
    disk_mark="$(mark_usage "$use_percent" "$DISK_WARNING" "$DISK_CRITICAL")"
    if is_critical_usage "$use_percent" "$DISK_CRITICAL"; then
      add_alert "🔴 **磁盘 ${mount} 使用率：** ${use_percent}"
    elif is_warning_usage "$use_percent" "$DISK_WARNING"; then
      add_alert "⚠️ **磁盘 ${mount} 使用率：** ${use_percent}"
    fi
    printf '| %s | %s | %s | %s | %s%s |\n' "$mount" "$size" "$used" "$avail" "$use_percent" "$disk_mark" >> "$BODY_FILE"
  done <<< "$disks_usage"

  append_body <<'EOF'

---

EOF
}

collect_security_info() {
  local permit_root_login password_policy last_login failed_login firewalld_status selinux_status
  permit_root_login="$(grep -E '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null || echo '未配置')"
  password_policy="$(chage -l root 2>/dev/null | grep -E 'Maximum|最大|minimum|最小|Last|最近' || true)"
  last_login="$(last -n 5 2>/dev/null | grep -v begins || true)"
  failed_login="$(lastb -n 5 2>/dev/null | grep -v begins || true)"
  firewalld_status="$(systemctl is-active firewalld >/dev/null 2>&1 && echo '✅ 运行中' || echo '❌ 未运行')"
  selinux_status="$(getenforce 2>/dev/null || echo '未安装/未启用')"

  [[ "$permit_root_login" == *"PermitRootLogin yes"* ]] && add_alert "⚠️ **Root 远程登录：** ${permit_root_login}"
  [[ "$firewalld_status" == *"未运行"* ]] && add_alert "⚠️ **防火墙状态：** ${firewalld_status}"

  append_body <<EOF
## 三、安全配置

- **Root 远程登录检查：** \`${permit_root_login}\`
- **防火墙状态：** ${firewalld_status}
- **SeLinux 状态：** \`${selinux_status}\`

### 密码策略

\`\`\`text
${password_policy:-无}
\`\`\`

### 最近登录记录

\`\`\`text
${last_login:-无}
\`\`\`

EOF

  if [[ -n "$failed_login" ]]; then
    append_body <<EOF
### 失败登录记录

\`\`\`text
${failed_login}
\`\`\`

EOF
  fi

  append_body <<'EOF'
---

EOF
}

collect_service_status() {
  append_body <<'EOF'
## 四、服务与进程状态

EOF

  local item service_name candidates loaded_service candidate status_text
  for item in "${SERVICES[@]}"; do
    service_name="${item%%:*}"
    candidates="${item#*:}"
    loaded_service=""
    IFS=',' read -r -a candidate_array <<< "$candidates"
    for candidate in "${candidate_array[@]}"; do
      if [[ "$(systemctl show -p LoadState --value "$candidate" 2>/dev/null)" == "loaded" ]]; then
        loaded_service="$candidate"
        break
      fi
    done
    [[ -z "$loaded_service" ]] && continue
    status_text="$(systemctl is-active "$loaded_service" 2>/dev/null || true)"
    if [[ "$status_text" == "active" ]]; then
      printf -- '- **%s：** ✅ 运行中\n' "$service_name" >> "$BODY_FILE"
    elif [[ "$status_text" == "inactive" ]]; then
      printf -- '- **%s：** ❌ 未运行\n' "$service_name" >> "$BODY_FILE"
      add_alert "⚠️ **服务 ${service_name}：** 已安装但未运行"
    else
      printf -- '- **%s：** ⚠️ %s\n' "$service_name" "${status_text:-状态异常}" >> "$BODY_FILE"
      add_alert "⚠️ **服务 ${service_name}：** ${status_text:-状态异常}"
    fi
  done

  append_body <<'EOF'

---

EOF
}

collect_network_info() {
  local ports network
  if command -v netstat >/dev/null 2>&1; then
    ports="$(netstat -tupln 2>/dev/null | grep -E 'LISTEN' | awk '{print $4}' || true)"
  elif command -v ss >/dev/null 2>&1; then
    ports="$(ss -tupln 2>/dev/null | grep -E 'LISTEN' | awk '{print $5}' || true)"
  else
    ports="未安装 netstat/ss"
  fi
  network="$(ip -o -4 addr 2>/dev/null | awk '!/docker|veth|br-|cni|flannel|tun|kube/ && $2!="lo" {print $2, $4}' | uniq)"

  append_body <<EOF
## 五、网络与端口

### 开放端口列表

\`\`\`text
${ports:-无}
\`\`\`

EOF

  if [[ -n "$network" ]]; then
    append_body <<'EOF'
### 网卡地址信息

| 接口 | 地址 |
| --- | --- |
EOF
    while read -r iface addr; do
      [[ -n "${iface:-}" && -n "${addr:-}" ]] && printf '| %s | %s |\n' "$iface" "$addr" >> "$BODY_FILE"
    done <<< "$network"
    printf '\n' >> "$BODY_FILE"
  fi

  append_body <<'EOF'
---

EOF
}

collect_docker_status() {
  append_body <<'EOF'
## 六、Docker 容器状态

EOF

  if ! command -v docker >/dev/null 2>&1; then
    append_body <<'EOF'
未安装 docker，跳过容器巡检。

---

EOF
    return
  fi

  local context containers stats
  context="$(docker context show 2>&1)"
  if [[ $? -ne 0 ]]; then
    add_alert "⚠️ **Docker Context：** 查询失败，跳过容器巡检"
    append_body <<EOF
Docker context 查询失败，跳过容器巡检。

\`\`\`text
${context}
\`\`\`

---

EOF
    return
  fi

  if [[ "$context" != "default" ]]; then
    add_alert "⚠️ **Docker Context：** 当前为 ${context}，离线脚本不会自动切换 context，容器巡检已跳过"
    append_body <<EOF
当前 Docker context 为 \`${context}\`，离线脚本不会自动切换到 \`default\`，跳过容器巡检。

---

EOF
    return
  fi

  containers="$(docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>&1)"
  if [[ $? -ne 0 ]]; then
    add_alert "⚠️ **Docker 容器状态：** docker ps 查询失败"
  else
    while IFS= read -r line; do
      [[ "$line" == NAMES* ]] && continue
      if printf '%s' "$line" | grep -Eiq 'exited|unhealthy|dead|restarting'; then
        add_alert "⚠️ **Docker 异常容器：** ${line}"
      fi
    done <<< "$containers"
  fi
  stats="$(docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' 2>&1 || true)"

  append_body <<EOF
### 容器列表

\`\`\`text
${containers:-未发现容器。}
\`\`\`

### 容器资源占用

\`\`\`text
${stats:-未获取到容器资源占用。}
\`\`\`

---

EOF
}

collect_supervisor_status() {
  append_body <<'EOF'
## 七、Supervisor 子应用状态

EOF

  if ! command -v supervisorctl >/dev/null 2>&1; then
    append_body <<'EOF'
未安装 supervisorctl，跳过 Supervisor 子应用巡检。

---

EOF
    return
  fi

  local content
  content="$(supervisorctl status 2>&1 || true)"
  while IFS= read -r line; do
    if printf '%s' "$line" | grep -Eq '\b(FATAL|BACKOFF|STOPPED|EXITED|UNKNOWN)\b'; then
      add_alert "⚠️ **Supervisor 子应用异常：** ${line}"
    fi
  done <<< "$content"

  append_body <<EOF
### supervisorctl status

\`\`\`text
${content:-未发现 Supervisor 子应用。}
\`\`\`

---

EOF
}

collect_log_errors() {
  local journal_content log_path file_content
  append_body <<'EOF'
## 八、日志与系统错误

EOF

  if command -v journalctl >/dev/null 2>&1; then
    journal_content="$(journalctl --since "${LOG_DAYS} days ago" -p err..alert --no-pager 2>&1 | grep -viE 'systemd-coredump|ldapdb_canonuser_plug_init' | tail -n "$LOG_LINES" || true)"
    [[ -z "$journal_content" ]] && journal_content="未匹配到 err..alert 级别日志。"
    append_body <<EOF
### systemd journal 错误日志（最近 ${LOG_DAYS} 天内，最近 ${LOG_LINES} 行）

\`\`\`text
${journal_content}
\`\`\`

EOF
  else
    append_body <<'EOF'
### systemd journal 错误日志

```text
当前系统未安装 journalctl。
```

EOF
  fi

  for log_path in "${LOG_PATHS[@]}"; do
    [[ ! -f "$log_path" ]] && continue
    file_content="$(grep -aiE 'error|failed|fatal|panic|crit|critical|异常' "$log_path" 2>&1 | tail -n "$LOG_LINES" || true)"
    [[ -z "$file_content" ]] && file_content="文件存在，但未匹配到关键字日志。"
    append_body <<EOF
### 文件日志扫描：${log_path}（关键字匹配最近 ${LOG_LINES} 行）

\`\`\`text
${file_content}
\`\`\`

EOF
  done

  append_body <<'EOF'
---

EOF
}

collect_monitors() {
  local exporters exporter status_text
  exporters="$(systemctl list-unit-files 2>&1 | grep -i 'exporter' | awk '{print $1}' || true)"
  append_body <<'EOF'
## 九、监控状态

EOF

  if [[ -z "$exporters" ]]; then
    append_body <<'EOF'
未找到任何已安装的 exporter。

EOF
    return
  fi

  while IFS= read -r exporter; do
    [[ -z "$exporter" ]] && continue
    status_text="$(systemctl is-active "$exporter" 2>/dev/null || true)"
    if [[ "$status_text" == "active" ]]; then
      printf -- '- **%s：** ✅ 运行中\n' "$exporter" >> "$BODY_FILE"
    else
      printf -- '- **%s：** ☐ 未运行\n' "$exporter" >> "$BODY_FILE"
      add_alert "⚠️ **监控组件 ${exporter}：** 未运行"
    fi
  done <<< "$exporters"
  printf '\n' >> "$BODY_FILE"
}

write_report() {
  local hostname ipaddress timestamp report_dir now_str safe_hostname
  hostname="$(safe_cmd 'unknown-host' hostname | tr -d '/\\:*?"<>|')"
  [[ -z "$hostname" ]] && hostname="unknown-host"
  ipaddress="$(ip -o -4 addr 2>/dev/null | awk '!/docker|veth|br-|cni|flannel|kube/ && $2!="lo" {print $4}' | head -1 | cut -d/ -f1)"
  [[ -z "$ipaddress" ]] && ipaddress="127.0.0.1"
  timestamp="$(date +%Y%m)"
  now_str="$(date '+%Y-%m-%d %H:%M:%S')"
  report_dir="${REPORT_ROOT}/${GROUP}/${timestamp}"
  mkdir -p "$report_dir"
  safe_hostname="$hostname"
  REPORT_FILE="${report_dir}/${ipaddress}_${safe_hostname}.md"
  BODY_FILE="${REPORT_FILE}.body"
  : > "$BODY_FILE"

  collect_server_info
  collect_system_resources
  collect_security_info
  collect_service_status
  collect_network_info
  collect_docker_status
  collect_supervisor_status
  collect_log_errors
  collect_monitors

  {
    printf '# 服务器巡检报告 - %s (%s)\n\n' "$hostname" "$ipaddress"
    printf -- '- 生成时间：`%s`\n\n' "$now_str"
    printf -- '---\n\n'
    printf '## 风险摘要\n\n'
    if [[ ${#ALERTS[@]} -eq 0 ]]; then
      printf -- '- ✅ 未发现达到告警阈值的风险项。\n'
    else
      local alert
      for alert in "${ALERTS[@]}"; do
        printf -- '- %s\n' "$alert"
      done
    fi
    printf '\n---\n\n'
    cat "$BODY_FILE"
  } > "$REPORT_FILE"

  rm -f "$BODY_FILE"
  printf '巡检完成，报告已生成：%s\n' "$REPORT_FILE"
}

write_report
