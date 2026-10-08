# WebUI 发布与更新

本手册供 Linux 发布机的维护者使用；最终用户安装方法见 `README.md`。以下命令假设当前仓库的 `origin` 为 Gitee、`github` 为 GitHub，待发布分支为 `master`。先运行 `git remote -v` 核对发布机上的实际配置；不要在远端名称或地址不符时照抄推送命令。

## 发布前检查

```bash
git switch master
git pull --ff-only origin master
git fetch github master --tags
git remote -v
git status --short
git log --oneline github/master..HEAD
git diff --stat github/master..HEAD
git merge-base --is-ancestor github/master HEAD
```

审阅将要推送的**全部**提交与差异，确认没有真实资产或秘密。`git status --short` 应为空；最后一条命令返回非零时，停止发布并处理分支分歧，不要强推。`github/master` 可能比 `origin/master` 落后多个提交，发布 Release 前需要先将计划公开的源码推到 GitHub。

发布机需要 Linux `x86_64`、Docker Engine 和 GHCR 推送权限（例如使用有 `write:packages` 权限的令牌执行 `docker login ghcr.io`）。安装机需要能从公开 GHCR 拉取镜像。当前 `Dockerfile.webui` 的基础镜像标签和 `pyproject.toml` 的 Python 依赖尚未锁定；发布镜像按 digest 固定，但重建不保证一致。正式发布前固定基础镜像摘要和依赖版本，并在 Linux Docker 环境验证首次安装、重复运行和升级。

## 首次发布

当前脚本版本为 `0.1.2`；如果已修改版本，以 `scripts/install_webui.sh` 顶部的 `WEBUI_VERSION` 和 `pyproject.toml` 的版本为准，两者应保持一致。`--prepare-release` 直接以当前工作区构建并推送镜像，不执行提交状态和版本预检；发布前自行审阅源码。不要覆盖任何已发布的版本标签、镜像或附件。

```bash
VERSION=0.1.2
bash scripts/install_webui.sh --prepare-release

git push github master
git tag -a "v${VERSION}" -m "AutoDeployKit WebUI v${VERSION}"
git push github "v${VERSION}"

gh auth status
gh release create "v${VERSION}" \
  "dist/v${VERSION}/compose.webui.yaml" \
  "dist/v${VERSION}/install_webui.sh" \
  --repo zzyork/AutoDeployKit \
  --verify-tag \
  --title "AutoDeployKit WebUI v${VERSION}" \
  --notes "WebUI 镜像与在线安装脚本"
gh release view "v${VERSION}" --repo zzyork/AutoDeployKit
```

`gh` 需在发布机上已安装并登录，Git 推送也需要对应权限。首次推送 GHCR 包时须在 GitHub Packages 设置中确认其可匿名拉取；从无登录凭据的测试机验证 `docker pull`。生成的两个文件位于 `dist/v<版本>/`，必须上传到**同一个**公开可下载的 `v<版本>` Release；附件固定命名为 `install_webui.sh` 与 `compose.webui.yaml`。不要单独分发仓库中的模板脚本。旧安装脚本已固定其镜像 digest 和 Compose 哈希，不得重用旧版本号。`dist/` 已被 Git 忽略，不提交发布产物。

## 后续版本

每次使用新版本号，例如 `0.1.3`。先修改 `scripts/install_webui.sh` 的 `WEBUI_VERSION`、`pyproject.toml` 的 `version`，并按仓库规则更新 `docs/PROJECT_INVENTORY.md` 的变更记录；如有其他代码改动，一并审阅并只暂存本次涉及的文件。

```bash
VERSION=0.1.3
${EDITOR:-vi} scripts/install_webui.sh pyproject.toml docs/PROJECT_INVENTORY.md
git diff --check
git diff
git status --short
git add scripts/install_webui.sh pyproject.toml docs/PROJECT_INVENTORY.md
# 其他本次修改的源码请逐一 git add 对应路径，不要使用 git add .
git commit -m "feat: release WebUI v${VERSION}"
git push origin master
```

随后重新执行“发布前检查”和“首次发布”中的制品生成、推送及 Release 命令，将 `VERSION` 改为新版本；勿对旧标签执行覆盖上传。

## 发布后验证

确认 GitHub Release 页面有两个附件，安装脚本中的版本、Compose 哈希与镜像 digest 匹配，且镜像无需登录即可拉取。应在独立 Linux Docker 主机通过已发布的脚本验收首次安装、同版本重复运行及使用新版本脚本升级；首次安装需交互终端显示管理员口令，升级后检查各网卡 IPv4 的 HTTPS 证书、访问入口及备份目录。安装及升级时使用同一个安装目录和端口；安装目录保存部署文件和备份，数据库/报告与加密根密钥仍分别存放在 Docker 命名卷中。

在**测试主机**的交互终端执行；升级时将版本号改为新版本，安装提示中输入与原安装相同的目录和端口：

```bash
VERSION=0.1.2
mkdir -p "v${VERSION}"
curl -fL -o "v${VERSION}/install_webui.sh" \
  "https://github.com/zzyork/AutoDeployKit/releases/download/v${VERSION}/install_webui.sh"
sudo bash "v${VERSION}/install_webui.sh"
```

如使用其他 HTTPS 附件下载源，需将**相同的 Compose 文件**放在 `<下载源>/v<版本>/compose.webui.yaml`。目标主机通过 `AUTODEPLOYKIT_WEBUI_DOWNLOAD_BASE_URL` 指定该 HTTPS 基础地址；镜像仍从 GHCR 拉取。源不可用、哈希不一致或镜像拉取失败时脚本会中止，不会自动回退 GitHub。发布机不执行实际生产服务器安装或升级。
