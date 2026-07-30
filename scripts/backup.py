"""一键备份 SQLite 数据库和 ChromaDB 向量库。

用法示例：
    # 使用默认参数（数据目录 = 项目根目录，备份到 ./backups/，保留 7 个）
    python scripts/backup.py

    # 自定义数据目录和备份目录，只保留最近 3 个备份
    python scripts/backup.py --data-dir ./data --backup-dir /mnt/backups --keep 3
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path


def _resolve_data_dir(data_dir: str | None) -> Path:
    """确定数据目录：命令行参数 > 环境变量 DATA_DIR > 项目根目录。"""
    if data_dir:
        return Path(data_dir).resolve()
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    # 脚本位于 scripts/，项目根目录是其父目录
    return Path(__file__).resolve().parents[1]


def _backup_sqlite(db_path: Path, dest_dir: Path) -> Path:
    """使用 sqlite3 backup API 安全备份数据库，返回备份文件路径。"""
    if not db_path.exists():
        print(f"[警告] 数据库文件不存在，跳过：{db_path}")
        return dest_dir / db_path.name

    backup_path = dest_dir / db_path.name
    print(f"[备份] SQLite 数据库：{db_path} -> {backup_path}")

    source = sqlite3.connect(str(db_path))
    target = sqlite3.connect(str(backup_path))
    try:
        # backup() 会在同一进程内安全复制，避免文件锁问题
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()

    return backup_path


def _collect_chroma_files(chroma_dir: Path, dest_dir: Path) -> Path | None:
    """将 chroma_db/ 目录复制到临时目录，返回复制后的目录路径。"""
    if not chroma_dir.exists():
        print(f"[警告] ChromaDB 目录不存在，跳过：{chroma_dir}")
        return None

    import shutil

    dest = dest_dir / chroma_dir.name
    print(f"[备份] ChromaDB 目录：{chroma_dir} -> {dest}")
    shutil.copytree(str(chroma_dir), str(dest), dirs_exist_ok=True)
    return dest


def _create_archive(backup_dir: Path, timestamp: str, staging_dir: Path) -> Path:
    """将暂存目录打包为 tar.gz，返回压缩包路径。"""
    archive_name = f"backup_{timestamp}.tar.gz"
    archive_path = backup_dir / archive_name
    print(f"[打包] 创建压缩备份：{archive_path}")

    with tarfile.open(str(archive_path), "w:gz") as tar:
        for item in staging_dir.iterdir():
            tar.add(str(item), arcname=item.name)

    return archive_path


def _cleanup_old_backups(backup_dir: Path, keep: int) -> None:
    """删除旧备份，只保留最近 keep 个。"""
    backup_files = sorted(
        backup_dir.glob("backup_*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    to_remove = backup_files[keep:]
    if not to_remove:
        print(f"[清理] 当前共 {len(backup_files)} 个备份，无需清理（保留 {keep} 个）")
        return

    for old_backup in to_remove:
        print(f"[清理] 删除旧备份：{old_backup}")
        old_backup.unlink()

    print(
        f"[清理] 已删除 {len(to_remove)} 个旧备份，保留最近 {keep} 个"
    )


def run_backup(
    data_dir: Path,
    backup_dir: Path,
    keep: int,
) -> Path:
    """执行完整备份流程，返回最终压缩包路径。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 使用临时目录作为打包前的暂存区
    with tempfile.TemporaryDirectory(prefix="backup_staging_") as tmp:
        staging_dir = Path(tmp)

        # 1. 备份 SQLite 数据库
        db_path = data_dir / "tutor_agent.db"
        sqlite_backup = _backup_sqlite(db_path, staging_dir)

        # 2. 复制 ChromaDB 目录
        chroma_dir = data_dir / "chroma_db"
        _collect_chroma_files(chroma_dir, staging_dir)

        # 3. 打包压缩
        archive_path = _create_archive(backup_dir, timestamp, staging_dir)

    # 4. 清理旧备份
    _cleanup_old_backups(backup_dir, keep)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"\n[完成] 备份成功：{archive_path}（{size_mb:.2f} MB）")
    return archive_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="一键备份 SQLite 数据库和 ChromaDB 向量库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="数据目录（默认：环境变量 DATA_DIR 或项目根目录）",
    )
    parser.add_argument(
        "--backup-dir",
        default="./backups/",
        help="备份输出目录（默认：./backups/）",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="保留最近 N 个备份，自动清理旧备份（默认：7）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = _resolve_data_dir(args.data_dir)
    backup_dir = Path(args.backup_dir).resolve()

    print(f"[配置] 数据目录：{data_dir}")
    print(f"[配置] 备份目录：{backup_dir}")
    print(f"[配置] 保留数量：{args.keep}")
    print()

    if not data_dir.exists():
        print(f"[错误] 数据目录不存在：{data_dir}", file=sys.stderr)
        return 1

    run_backup(data_dir=data_dir, backup_dir=backup_dir, keep=args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
