import hashlib
import time
import const
import os
import shutil
import requests
import html
import traceback
import subprocess
import re
import json
from tqdm import tqdm
from download import DownloadPool
from avalon import Avalon


class RetryError(Exception):
    pass


class RetryExhausted(RetryError):
    pass


class RetryCheckFailed(RetryError):
    pass


class UserCancelled(Exception):
    pass


class TiebaApiError(Exception):
    pass


class UndifiedMsgType(TiebaApiError):
    pass


class RequestError(TiebaApiError):
    def __init__(self, data):
        self.data = data


const.PageUrl = "http://c.tieba.baidu.com/c/f/pb/page"
const.FloorUrl = "http://c.tieba.baidu.com/c/f/pb/floor"
const.EmotionUrl = "http://tieba.baidu.com/tb/editor/images/client/"
const.AliUrl = "https://tieba.baidu.com/tb/editor/images/ali/"
const.VoiceUrl = "http://c.tieba.baidu.com/c/p/voice?play_from=pb_voice_play&voice_md5="
const.SignKey = "tiebaclient!!!"
# const.IS_WIN=(os.name=="nt")


def MakeDir(dirname):
    global IsCreate
    if (dirname in IsCreate):
        return
    if (os.path.isdir(dirname)):
        pass
    elif (os.path.exists(dirname)):
        raise OSError("%s is a file" % dirname)
    else:
        os.makedirs(dirname)
    IsCreate.add(dirname)


def Init(pid, overwrite):
    global FileHandle, Progress, AudioCount, VideoCount, ImageCount,\
        Pool, IsDownload, DirName, IsCreate, OutputHTML, FFmpeg
    IsDownload = set()
    IsCreate = set()
    AudioCount = VideoCount = ImageCount = 0
    if (os.path.isdir(DirName)):
        Avalon.warning("\"%s\"已存在" % DirName)
        if (overwrite == 1):
            Avalon.warning("跳过%d" % pid)
        elif (overwrite == 2):
            Avalon.warning("默认覆盖\"%s\"" % DirName)
        elif (not Avalon.ask("是否覆盖?", False)):
            raise UserCancelled("...")
    elif (os.path.exists(DirName)):
        raise OSError("存在同名文件")
    else:
        os.makedirs(DirName)
    if (OutputHTML):
        FileHandle = open("%s/%d.html" % (DirName, pid), "w", encoding="utf-8")
        Write('<!doctype html><html lang="zh-cn"><head><link rel="stylesheet"'
              ' type="text/css" href="main.css"></head><body><div id="write">')
        shutil.copy("main.css", DirName+"/")
    else:
        FileHandle = open("%s/%d.md" % (DirName, pid), "w", encoding="utf-8")
    try:
        subprocess.Popen("ffmpeg", stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL).wait()
        FFmpeg = 1
    except FileNotFoundError:
        Avalon.warning("未找到ffmpeg,语音将不会被转为mp3")
        FFmpeg = 0
    Pool = DownloadPool(DirName+"/", "file")
    Progress = tqdm(unit="floor")


def ConvertAudio():
    global AudioCount, DirName, FFmpeg
    if ((not FFmpeg) or (not AudioCount)):
        return
    for i in tqdm(range(1, AudioCount+1), unit="audio", ascii=True):
        if (FFmpeg):
            prefix = "%s/audios/%d" % (DirName, i)
            subprocess.Popen(["ffmpeg", "-i", "%s.amr" % prefix,
                              "%s.mp3" % prefix, "-y"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL).wait()
            os.remove("%s.amr" % prefix)


def Done():
    global OutputHTML
    if (OutputHTML):
        Write('</div></body></html>')
    FileHandle.close()
    Progress.set_description("Waiting for the download thread...")
    Pool.Stop()
    Progress.close()


def ForceStop():
    if ("FileHandle" in globals().keys()):
        FileHandle.close()
    if ("Pool" in globals().keys()):
        Pool.ImgProc.close()
    if ("Progress" in globals().keys()):
        Progress.close()


def CallFunc(func=None, args=None, kwargs=None):
    if (not (func is None)):
        if (args is None):
            if (kwargs is None):
                return func()
            else:
                return func(**kwargs)
        else:
            if (kwargs is None):
                return func(*args)
            else:
                return func(*args, **kwargs)

# times == -1 ---> forever


def Retry(func, args=None, kwargs=None, cfunc=None, ffunc=None, fargs=None, fkwargs=None, times=3, sleep=1):
    fg = 0
    while (times):
        try:
            resp = CallFunc(func, args, kwargs)
        except Exception as err:
            CallFunc(ffunc, fargs, fkwargs)
            times = max(-1, times-1)
            time.sleep(sleep)
        else:
            if (CallFunc(cfunc, (resp,)) in [None, True]):
                return resp
            times = max(-1, times-1)
            fg = 1
    if (fg):
        raise RetryCheckFailed(func.__qualname__, args, cfunc.__qualname__, resp)
    else:
        raise RetryExhausted(func.__qualname__, args, cfunc.__qualname__) from err


def Write(content):
    FileHandle.write(content)


def SignRequest(data):
    s = ""
    keys = sorted(data.keys())
    for i in keys:
        s += i + "=" + data[i]
    sign = hashlib.md5((s + const.SignKey).encode("utf-8")).hexdigest().upper()
    data.update({"sign": str(sign)})
    return data


def TiebaRequest(url, data, first=False):
    if (first):
        req = Retry(requests.post, args=(url,), kwargs={"data": SignRequest(data)},
                    cfunc=(lambda x: x.status_code == 200), ffunc=print,
                    fargs=("Connect Failed,Retrying...\n",), times=5)
    else:
        req = Retry(requests.post, args=(url,), kwargs={"data": SignRequest(data)},
                    cfunc=(lambda x: x.status_code == 200), ffunc=Progress.set_description,
                    fargs=("Connect Failed,Retrying...",), times=5)
    req.encoding = 'utf-8'
    ret = req.json()
    if (int(ret["error_code"]) != 0):
        raise RequestError({"code": int(ret["error_code"]), "msg": str(ret["error_msg"])})
    return req.json()


def ReqContent(pid, fid, lz):
    if (~fid):
        return TiebaRequest(const.PageUrl, {"kz": str(pid), "pid": str(fid), "lz": str(int(lz)), "_client_version": "9.9.8.32"})
    else:
        return TiebaRequest(const.PageUrl, {"kz": str(pid), "lz": str(int(lz)), "_client_version": "9.9.8.32"})


def ReqComment(pid, fid, pn):
    return TiebaRequest(const.FloorUrl, {"kz": str(pid), "pid": str(fid), "pn": str(pn), "_client_version": "9.9.8.32"})


def FormatTime(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(t)))


def ProcessText(text, in_comment):
    global OutputHTML
    if (OutputHTML):
        if (in_comment):
            return html.escape(text)
        else:
            return html.escape(text).replace("\n", "<br />")
    else:
        if (in_comment):
            return html.escape(text)
        else:
            return html.escape(text).replace("\\", "\\\\").replace("\n", "  \n").replace("*", "\\*")\
                .replace("-", "\\-").replace("_", "\\_").replace("(", "\\(").replace(")", "\\)")\
                .replace("#", "\\#").replace("`", "\\`").replace("~", "\\~").replace("[", "\\[")\
                .replace("]", "\\]").replace("!", "\\!").replace(".", "\\.").replace("+", "\\+")


def ProcessUrl(url, text):
    return '<a href="%s">%s</a>' % (url, text)


def ProcessImg(url):
    global ImageCount, DirName
    if (url[0:2] == "//"):
        url = "http:"+url
    MakeDir(DirName+"/images")
    ImageCount += 1
    name = "images/%d.%s" % (ImageCount, url.split("?")[0].split(".")[-1])
    Pool.Download(url, name)
    return '\n<div><img src="%s" /></div>\n' % name


def ProcessVideo(url, cover):
    global VideoCount, DirName, OutputHTML
    MakeDir(DirName+"/videos")
    VideoCount += 1
    vname = "videos/%d.%s" % (VideoCount, url.split(".")[-1])
    cname = "videos/%d_cover.%s" % (VideoCount, cover.split(".")[-1])
    Pool.Download(url, vname)
    Pool.Download(cover, cname)
    if (OutputHTML):
        return '\n<video src="%s" poster="%s" controls />\n' % (vname, cname)
    else:
        return '\n<a href="%s"><img src="%s" title="点击查看视频"></a>\n' % (vname, cname)


def ProcessAudio(md5):
    global AudioCount, DirName, OutputHTML, FFmpeg
    MakeDir(DirName+"/audios")
    AudioCount += 1
    Pool.Download(const.VoiceUrl+md5, "audios/%d.amr" % AudioCount)
    if (OutputHTML and FFmpeg):
        return '<audio src="audios/%d.mp3" controls />' % AudioCount
    elif (FFmpeg):
        return '<a href="audios/%d.mp3">语音</a>\n' % AudioCount
    else:
        return '<a href="audios/%d.amr">语音</a>\n' % AudioCount


def ProcessEmotion(floor, name, text):
    global DirName, IsDownload
    MakeDir(DirName+"/images")
    lname = len(name)
    if (name == "image_emoticon"):
        name += "1"
        lname += 1
    url = ""
    if (lname >= 3 and name[0:3] == "ali"):
        url = "%s%s.gif" % (const.AliUrl, name)
        name += ".gif"
    elif (lname >= 14 and name[0:14] == "image_emoticon"):
        url = "%s%s.png" % (const.EmotionUrl, name)
        name += ".png"
    else:
        Avalon.warning("第%s楼出现未知表情:%s\n" % (floor, name), front="\n")
        return ''
    if (not name in IsDownload):
        IsDownload.add(name)
        Pool.Download(url, "images/%s" % name)
    return '<img src="images/%s" alt="%s" title="%s" />' % (name, text, text)


def ProcessContent(floor, data, in_comment):
    content = ""
    for s in data:
        if (str(s["type"]) == "0"):
            content += ProcessText(s["text"], in_comment)
        elif (str(s["type"]) == "1"):
            content += ProcessUrl(s["link"], s["text"])
        elif (str(s["type"]) == "2"):
            content += ProcessEmotion(floor, s["text"], s["c"])
        elif (str(s["type"]) == "3"):
            content += ProcessImg(s["origin_src"])
        elif (str(s["type"]) == "4"):
            content += ProcessText(s["text"], in_comment)
        elif (str(s["type"]) == "5"):
            content += ProcessVideo(s["link"], s["src"])
        elif (str(s["type"]) == "9"):
            content += ProcessText(s["text"], in_comment)
        elif (str(s["type"]) == "10"):
            content += ProcessAudio(s["voice_md5"])
        elif (str(s["type"]) == "11"):
            content += ProcessImg(s["static"])
        elif (str(s["type"]) == "20"):
            content += ProcessImg(s["src"])
        else:
            Avalon.warning("floor %s: content data wrong: \n%s\n" % (floor, str(s)), front="\n")
            # raise UndifiedMsgType("content data wrong: \n%s\n"%str(s))
    return content


def ProcessFloor(floor, author, t, content):
    global OutputHTML
    if (OutputHTML):
        return '<hr />\n<div>%s</div><br />\n<div class="author">\
            %s楼 | %s | %s</div>\n' % (content, floor, author, FormatTime(t))
    else:
        return '<hr />\n\n%s\n<div align="right" style="font-size:12px;color:#CCC;">\
            %s楼 | %s | %s</div>\n' % (content, floor, author, FormatTime(t))


def ProcessComment(author, t, content):
    return '%s | %s:<blockquote>%s</blockquote>' % (FormatTime(t), author, content)


def GetComment(floor, pid, fid):
    global OutputHTML
    if (OutputHTML):
        Write('<pre>')
    else:
        Write('<pre style="background-color: #f6f8fa;border-radius: 3px;\
            font-size: 85%;line-height: 1.45;overflow: auto;padding: 16px;">')
    pn = 1
    while (1):
        data = ReqComment(pid, fid, pn)
        data = data["subpost_list"]
        if (len(data) == 0):
            break
        for comment in data:
            Write(ProcessComment(comment["author"]["name_show"], comment["time"], ProcessContent(floor, comment["content"], 1)))
        pn += 1
    Write('</pre>')


def ProcessUserList(data):
    userlist = {}
    for user in data:
        userlist[user["id"]] = {"id": user["portrait"].split("?")[0], "name": user["name_show"]}
    return userlist


def GetTitle(pid):
    data = TiebaRequest(const.PageUrl, {"kz": str(pid), "_client_version": "9.9.8.32"}, True)
    return {"post": data["post_list"][0]["title"], "forum": data["forum"]["name"]}


def GetPost(pid, lz, comment):
    lastfid = -1
    while (1):
        data = ReqContent(pid, lastfid, lz)
        # print(data)
        userlist = ProcessUserList(data["user_list"])
        for floor in data["post_list"]:
            if (int(floor["id"]) == lastfid):
                continue
            fnum = floor["floor"]
            Progress.update(1)
            Progress.set_description("Collecting floor %s" % fnum)
            fid = int(floor["id"])
            Write(ProcessFloor(fnum, userlist[floor["author_id"]]["name"], floor["time"], ProcessContent(fnum, floor["content"], 0)))
            if (int(floor["sub_post_number"]) == 0):
                continue
            if (comment):
                GetComment(fnum, pid, floor["id"])
        if (lastfid == fid):
            break
        # print(fid,lastfid)
        lastfid = fid


def send_wxmsg(_sckey, _title="标题", _context="正文"):
    url = "https://sc.ftqq.com/%s.send" % (_sckey)
    _context = _context + "     " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    data = {
        "text": "%s" % (_title),
        "desp": "%s" % (_context)
    }
    try:
        res = requests.post(url=url, data=data)
        msg_back = json.loads(res.text)
        if msg_back["errmsg"] == "success":
            Avalon.info("返回值：%s" % (msg_back["errmsg"]))
        else:
            Avalon.warning("返回值：%s" % (msg_back["errmsg"]))
    except Exception:
        Avalon.error("消息发送错误")



'''
while (1):
    try:
        if (Avalon.ask("批量模式?", False)):
            PreSet = True
            lz = Avalon.ask("只看楼主?", False)
            comment = (0 if lz else Avalon.ask("包括评论?", True))
            OutputHTML = Avalon.ask("输出HTML(否则表示输出Makrdown)?:", True)
            overwrite = Avalon.ask("默认覆盖?", False)
            Avalon.info("选定:%s && %s评论 , 目录:\"吧名\\标题\"" % (("楼主" if lz else "全部"), ("全" if comment else "无")))
            if (not Avalon.ask("确认无误?", True)):
                Avalon.warning("请重新输入")
            else:
                break
        else:
            PreSet = False
            break
    except KeyboardInterrupt:
        ForceStop()
        Avalon.error("Control-C,exiting", front="\n")
        exit(0)
'''

'''
#####################
#                   #
#    Code START     #
#                   #
#####################
'''
PreSet = False  # 批量模式关
overwrite = 2  # 1为跳过，2为默认覆盖
sckey = ""  # 可选
while (1):
    try:
        pid = 123456789  # 帖子id，请修改
        if (pid == 0):
            exit(0)
        Avalon.info("当前时间: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(time.time()))))
        Avalon.info("帖子id: %d" % pid)
        title = GetTitle(pid)
        title["forum"] = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_", title["forum"])
        title["post"] = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_", title["post"])
        if (not PreSet):
            #  lz = Avalon.ask("只看楼主?", False)
            lz = False
            Avalon.info("只看楼主: " + str(lz))
            #  comment = (0 if lz else Avalon.ask("包括评论?", True))
            '''只看楼主模式下，爬取楼中楼待测试 --- 测试通过'''
            comment = True
            Avalon.info("包括评论: " + str(comment))
            #  DirName = Avalon.gets("文件夹名(空则表示使用\"吧名\\标题\"):")
            DirName = "saved_all"
            Avalon.info("目录名: " + DirName)
            if os.path.exists(DirName):  # 备份一下本地已经爬到的文件
                Avalon.info("备份本地已经爬到的文件")
                try:
                    os.rename(DirName, DirName + "-" + time.strftime("%Y%m%d-%Hh", time.localtime(int(time.time()))))
                except OSError:
                    Avalon.info("备份文件已经存在")
            #  OutputHTML = Avalon.ask("输出HTML(否则表示输出Makrdown)?:", True)
            OutputHTML = True
            Avalon.info("输出为Html: " + str(OutputHTML))
            if (len(DirName) == 0):
                DirName = title["forum"]+"\\"+title["post"]
            Avalon.info("id: %d , 选定: %s && %s评论 , 目录: \"%s\"" % (pid, ("楼主" if lz else "全部"), ("全" if comment else "无"), DirName))
            Init(pid, overwrite)
        else:
            DirName = title["forum"]+"\\"+title["post"]
            Init(pid, int(overwrite)+1)
        GetPost(pid, lz, comment)
        Done()
        ConvertAudio()
    except KeyboardInterrupt:
        ForceStop()
        Avalon.error("Control-C,exiting", front="\n")
        exit(0)
    except UserCancelled:
        Avalon.warning("用户取消")
    except RequestError as err:
        err = err.data
        Avalon.error("百度贴吧API返回错误,代码:%d\n描述:%s" % (err["code"], err["msg"]), front="\n")
    except Exception as err:
        ForceStop()
        Avalon.error("发生异常:\n"+traceback.format_exc(), front="\n")
        exit(0)
    else:
        Avalon.info("删除3天以前的备份...")
        Dirname_backuped = DirName + "-" + time.strftime("%Y%m%d-%Hh", time.localtime(int(time.time())-86400*3))
        if os.path.exists(Dirname_backuped):
            os.removedirs(Dirname_backuped)
            Avalon.info("删除完毕")
        else:
            Avalon.warning("未发现3天前的备份，跳过")
        if not sckey == "":
            Avalon.info("尝试向Server酱推送消息……")
            send_wxmsg(_sckey=sckey, _title="贴吧备份-全部楼层", _context="今日份的备份已完成...一切顺利..Maybe..")
        else:
            Avalon.warning("SCKEY为空，跳过微信推送")
        Avalon.info("完成 %d" % pid)
    if (not PreSet):
        break
