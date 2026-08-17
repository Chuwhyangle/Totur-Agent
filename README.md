# labs — 小项目沙箱

Totur-Agent 仓库的 orphan 分支，与 `main` 无共同祖先，**永不合并**。

## 为什么是 orphan 分支

主项目根目录被 FastAPI 应用占满（`app/`、`tests/`、`pytest.ini`、`Dockerfile`）。
小项目若直接放进主分支目录，会造成：顶层包名 `app/` 冲突、根 pytest 误收集、
Docker 构建上下文膨胀、`.gitignore` 无锚定条目误伤。
orphan 分支 + worktree 让两套代码在磁盘上并存而在版本控制上完全隔离。

## 使用

```powershell
# 首次 clone 仓库后需要重建 worktree（分支已存在，不加 --orphan）
git worktree add .worktrees\labs labs

# 日常开发
cd .worktrees\labs
```

在这个目录里 `git add / commit / push` 全部落在 `labs` 分支，
主项目根目录的 `git status` 永远看不到这些文件。

**AI 工具提示**：`.worktrees` 既是隐藏目录又被主分支 gitignore，
ripgrep 双重跳过 —— 从主项目根 workspace 搜不到这里的文件。
需要把 `.worktrees\labs` 作为**独立 workspace 根**打开。

## 项目索引

| 项目 | 语言/栈 | 状态 | 一句话说明 |
| --- | --- | --- | --- |
| _(空)_ | | | |

## 毕业（某个项目长大后独立出去）

```powershell
git subtree split --prefix=<name> -b <name>-export
git push git@github.com:Chuwhyangle/<name>.git <name>-export:main
# 然后在 labs 分支：git rm -r <name> && git commit -m "chore: graduate <name>"
```