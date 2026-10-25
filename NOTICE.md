# 第三方组件与致谢 / Third-party notices

本项目整体以 **GPL-3.0** 发布（见 `LICENSE`）。原因：拼音词库数据来自 GPL-3.0 项目 rime-ice，含词库的发行包需按 GPL-3.0 分发。

| 组件 | 用途 | 许可证 |
|---|---|---|
| [rime-ice 雾凇拼音](https://github.com/iDvel/rime-ice) | 拼音词库数据（8105 字 + 基础词库 + 扩展词库，含词频与注音）。运行 `python build_dict.py --download` 时下载，**不随源码仓库提交** | GPL-3.0 |
| [pygame-ce](https://github.com/pygame-community/pygame-ce)（含 SDL2） | 窗口、绘图、手柄输入 | LGPL-2.1 |
| [segno](https://github.com/heuer/segno) | 生成二维码 | BSD-3-Clause |
| [PyInstaller](https://pyinstaller.org/) | 打包 exe（仅开发用） | GPL-2.0 + 打包例外 |
| 微软雅黑 / Segoe UI Symbol | 界面字体，使用系统自带字体，**不随仓库分发** | Windows 自带 |

rime-ice 词库的上游来源（见其 README）：华宇野风系统词库、清华大学开源词库 THUOCL、现代汉语常用词表、腾讯词向量等。感谢这些项目。
