# Loon 去广告模块索引

> 在线访问：**https://hahapkpk.github.io/loon-index/**

自动跟踪 [ifflagged/Romeo](https://github.com/ifflagged/Romeo) 镜像库 `Modules/Loon/` 下的全部
Loon 去广告 / 增强模块（30+ 位作者的分享脚本），生成一个可以直接打开的网页：
按更新时间排序、中文名显示、一键复制源码地址导入 Loon。

完整项目说明（架构 / 机制 / 操作 / FAQ / 维护手册）见 **[项目说明.md](项目说明.md)**。

## 更新机制

- **自动**：GitHub Actions 每 3 小时拉取镜像库最新提交 → 重新生成 `data.js` → 部署到 GitHub Pages
  （构建在 GitHub 服务器上运行，本地电脑关机也照常更新）；
- **手动**：打开 [Actions 页面](https://github.com/hahapkpk/loon-index/actions/workflows/update-data.yml)
  点 `Run workflow`，或命令行执行：

  ```bash
  gh workflow run update-data.yml
  ```

最近一次更新时间记录在 `.state/last-update.txt`。

## 页面上怎么用

- 打开网页后默认按「最近更新」倒序排列；
- 顶部快捷筛选：今天 / 近 3 天 / 近 7 天 / 近 30 天；支持中英文名、作者、文件名搜索
  （快捷键 `/` 聚焦，`Esc` 清空）；
- 每行 **复制** = 复制 raw 源码地址 → Loon「插件 → 右上角 + → URL」粘贴导入；
- 手机浏览器点 **导入** 可直接唤起 Loon；
- **★ 关注** 收藏常用软件（保存在本机浏览器）；「按软件聚合」把同一软件的主线 / Beta / 官方版本折叠展示；
- 同步失败残留与空壳文件、依赖组件默认隐藏，可在筛选栏勾选显示。

## 中文名是怎么来的（顺序）

1. 插件文件头 `#!name` 自带中文名（约 4,300 个）；
2. 同软件跨作者自动对照（如 fmz200 的 `Zhihu.lpx` 借用 Kelee「知乎去广告」）；
3. `name_map.json` 兜底映射（英文名 token → 中文名）。

发现哪个软件还是英文显示，把 `文件名小写词干: "中文名"` 加进 `name_map.json` 即可
（下一轮自动更新生效，或手动触发一次）。

## 文件结构

| 文件 | 说明 |
|---|---|
| `index.html` | 页面本体（单文件，读同目录 `data.js`） |
| `build.py` | 数据构建脚本：增量拉取镜像库 → 取文件最后提交时间 → 解析插件头 → 生成 `data.js` |
| `name_map.json` | 英文名 → 中文名映射表 |
| `data.js` | 生成的数据（不入库，由 Actions / 本地构建生成） |
| `.github/workflows/update-data.yml` | 每 3 小时自动构建并部署的 Actions 工作流 |
| `refresh.bat` | Windows 一键本地刷新（等价于 `python build.py`） |
| `cache/` | 本地镜像库缓存（可随时删除，自动重建，约 1 分钟） |

## 本地运行（可选）

页面可完全离线使用：`index.html` 与 `data.js` 放在一起，直接双击即可。

```bash
python build.py     # 增量拉取镜像库 → 重新生成 data.js（需 Python 3 + git，通常 5–30 秒）
```

## 关于「更新日期」

显示的是镜像库中该文件的**最后提交时间**（本库这份副本最近一次变化的时间），
不是插件内 `#!date`（各作者格式不一，仅作参考显示在行详情里）。
镜像库自身每小时同步上游，偶发批量重写会让大量文件同时显示为「今天更新」，属正常现象。

## 依赖

Python 3（仅标准库）、git。
