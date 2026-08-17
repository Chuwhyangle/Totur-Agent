# AGENTS.md

本分支是**小项目沙箱**，与 `main` 分支的 Tutor Agent 主项目没有任何关系，
历史独立、永不合并。每个一级子目录是一个完全独立的项目。

## 硬规则

1. 子目录之间无依赖。禁止跨目录 import、共享代码或共享依赖。
2. 在某个子目录下工作时，以该目录自己的 AGENTS.md / README.md 为准。
   本文件只描述沙箱约定，不描述任何具体项目的技术栈。
3. 每个子目录自带独立 `.venv` 或 `node_modules`，不共用。
4. 分支根目录只放 README.md / AGENTS.md / .gitignore，不放业务代码、依赖或配置。
5. 不要引用、读取或假设主项目（FastAPI / Chroma / SQLite / MySQL trace 那一套）的存在。
   主项目的技术栈与命令**不适用于**这里。
6. 不要在本分支创建 `.github/workflows/`。
7. 永不执行 `git merge main` 或向 main 发 PR。

## 新增项目清单

1. `mkdir <name>` 并 `cd` 进去
2. 建独立虚拟环境（Python：`py -m venv .venv`）
3. 建该项目自己的 `AGENTS.md`、`README.md`、依赖清单
4. Python 项目在 `pyproject.toml` 写入以下内容，锚定 pytest rootdir，
   防止其向上层目录查找配置：

   [tool.pytest.ini_options]
   testpaths = ["tests"]

5. 回到分支根，在 README.md 索引表中登记一行