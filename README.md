# Codex 潮汐雷达

一个只读、中文优先的 Codex 公开数据监控台。它把重置预测、公开重置信号、模型效率、Fast 历史和额度摘要整理到一个轻量网页中，适合放在局域网或个人服务器长期运行。

这个仓库同时包含：

- `app.py`：标准库 Python 服务和公开数据轮询器。
- `static/index.html`：单页中文仪表盘。
- `compose.yaml`：Docker Compose 部署文件。
- `tests/`：不依赖网络的回归测试。
- `skill/`：可安装到 Codex 的维护/部署 Skill。

## 数据与隐私边界

- 只读取无需登录的公开接口；不读取 X、Codex 或 ChatGPT Cookie。
- 不调用模型，不消耗 Codex/ChatGPT 用量。
- 不接入投票、个人评分、任务协作或其他受限写接口。
- `data/state.json` 是运行时本地状态，包含历史去重和抓取结果，不应提交到公开仓库。
- 公开部署前请检查端口、防火墙和反向代理，不要把局域网管理地址写进源码或文档。

当前公开数据来源：

- [codex-reset.com](https://codex-reset.com/)：重置预测、时间线和公开事件。
- [codexradar.com](https://codexradar.com/)：公开摘要、模型众测和 Fast 历史。

## 本地运行

需要 Python 3.12+。项目只使用 Python 标准库：

```powershell
$env:PORT = "8080"
$env:POLL_SECONDS = "600"
$env:DATA_DIR = "./data"
python -u app.py
```

打开 `http://127.0.0.1:8080/`。首次成功轮询只建立事件基线，后续才会标记新事件。

## Docker Compose

```bash
docker compose up -d
```

默认监听宿主机 `17867` 端口。Compose 将 `data/` 单独挂载，更新代码时不要覆盖它；改完 `app.py` 或 `static/` 后执行：

```bash
docker compose up -d --force-recreate codex-reset-radar
```

## 验证

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py
```

健康检查：`GET /healthz`；状态接口：`GET /api/status`。

模型矩阵按 GPT 代际降序展示（GPT-6、GPT-5.6、GPT-5.5），同一模型内按 `low` 到 `ultra` 排列；这只是本地展示排序，不修改上游数据。

## Codex Skill

将 `skill/` 安装到 Codex 的 skills 目录即可使用：

```powershell
python install-skill-from-github.py `
  --repo kisser214/codex-tide-radar `
  --path skill
```

安装后可使用 `$codex-tide-radar` 请求检查、测试、维护或部署这套雷达。Skill 不会自动获得服务器、GitHub 或第三方账号权限；发生外部写入前仍需用户明确授权。

## 许可

本仓库暂未声明开源许可证。若要允许他人复用，请在 GitHub 仓库设置中补充合适的许可证。
