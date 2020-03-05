## 百度贴吧帖子备份

该分支基于master修改，是适合服务器部署的线上版本。

<p align="left">
<img src="https://img.shields.io/badge/Python-3.x-brightgreen?style=flat-square">
<img src="https://img.shields.io/github/license/hui-shao/TiebaBackup?color=orange&style=flat-square">
<img src="https://img.shields.io/badge/Platform-Windows%20%20%7C%20Linux-blue.svg?longCache=true&style=flat-square">
</p>


---

### Features

- 去除用户交互（参数请自行编辑脚本配置）
- 在"只看楼主" 模式默认开启保存楼中楼
- 接入 Server酱 消息推送
- 自动备份已爬取帖子，防止覆盖数据时出现意外（三天以前的备份自动删除）

![](https://github.com/hui-shao/TiebaBackup/blob/online/demo.png)
![](https://github.com/hui-shao/TiebaBackup/blob/online/wx.jpg)

### How to use:

<hr>

##### 环境配置

Linux:

```bash
apt-get install python3 python3-pip
pip3 install -r requirements.txt
python3 main.py
```

Windows:

在[官网](https://www.python.org/downloads/)下载python3.7或以上版本

```cmd
pip install -r requirements.txt
python3 main.py
```

<br>

##### 一些参数

| Var name       | Value                | Type          | Description       |
|:------------:  |:--------------------:|:-------------:|:-------------|
| PreSet         | True / **False**     | bool          | 批量模式（自动版暂不支持） |
| overwrite      | 1 / **2**            | int           |   是否覆盖（1为跳过，2为覆盖，其他值交互） |
| sckey          | "xxxxxxxxxxx"        | string        | 用于Server酱推送的Key，没有请留空 |
| pid            | 123456789            | int           | 帖子 ID |
| lz             | True / False         | bool          | 只看楼主模式 |
| comment        | **True** / False     | bool      | 是否包含楼中楼（评论） |
| DirName        | "xxxxxx"             | string        | 用于保存文件的目录名 |

<br>

##### 部署自动化(Linux)

使用 `crontab -e` 创建自动化，表示每天 11:30 和 23:30 时执行备份。例如：

```bash
30 11,23 * * * "python3" "/root/tieba_backup/main_all.py" >> /root/log1.txt 2>&1
```

<br>

还可以配合如下规则，以此实现每周六自动删除日志：

```bash
0 23 * * 6 rm /root/log1.txt
```

<br>

同时，也需要注意py文件的“换行符(Line-Ending)”，`CRLF / LF`

*另外建议 `vim .bashrc` , 注释掉其中的 `alias rm='rm -i'` 和 `alias cp='cp -i`，否则可能因为需要交互，导致程序暂停*

<br>

### Change log:

---

##### 2020.03.05

1. 诞生