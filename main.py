import urllib
import hashlib
import time
import const
import os
import shutil
import requests
import html
import sys
import traceback
from tqdm import tqdm
from download import DownloadPool
from avalon import Avalon

class RetryError(Exception):pass
class RetryExhausted(RetryError):pass
class RetryCheckFailed(RetryError):pass
class UserCancelled(Exception):pass
class TiebaApiError(Exception):pass
class UndifiedMsgType(TiebaApiError):pass
class RequestError(TiebaApiError):
    def __init__(self, data):
        self.data = data

const.PageUrl = "http://c.tieba.baidu.com/c/f/pb/page"
const.FloorUrl = "http://c.tieba.baidu.com/c/f/pb/floor"
const.EmotionUrl = "http://tieba.baidu.com/tb/editor/images/client/"
const.SignKey = "tiebaclient!!!"
# const.IS_WIN=(os.name=="nt")

# def GetEmotions():
#     for i in (list(range(1,51))+list(range(61,102))):
#         name="image_emoticon%d.png"%(i)
#         Pool.Download("https://tieba.baidu.com/tb/editor/images/client/"+name,"emotions/"+name)

def Init(pid,dirname):
    global FileHandle,Progress,ImgCount,Pool,IsDownload
    IsDownload=set()
    ImgCount=0
    if (os.path.isdir(dirname)):
        Avalon.warning("%s已存在"%dirname)
        if (not Avalon.ask("是否覆盖?",False)):
            raise UserCancelled
    elif (os.path.exists(dirname)):
        raise OSError("pid %d is a file."%pid)
    else:
        os.mkdir(dirname)
        os.mkdir(dirname+"/images")
    Pool=DownloadPool(dirname+"/images/","images")
    FileHandle=open("%s/%d.md"%(dirname,pid),"w",encoding="utf-8")
    Progress=tqdm(unit="floor")

def Done():
    FileHandle.close()
    Progress.set_description("Waiting for the image download thread...")
    Pool.Stop()
    Progress.close()

def ForceStop():
    if ("FileHandle" in globals().keys()):
        FileHandle.close()
    if ("Pool" in globals().keys()):
        Pool.ImgProc.close()
    if ("Progress" in globals().keys()):
        Progress.close()

def CallFunc(func=None,args=None,kwargs=None):
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
                return func(*args,**kwargs)

# times == -1 ---> forever
def Retry(func,args=None,kwargs=None,cfunc=None,ffunc=None,fargs=None,fkwargs=None,times=3,sleep=1):
    fg=0
    while (times):
        try:
            resp=CallFunc(func,args,kwargs)
        except Exception as err:
            CallFunc(ffunc,fargs,fkwargs)
            times=max(-1,times-1)
            time.sleep(sleep)
        else:
            if (CallFunc(cfunc,(resp,)) in [None,True]):
                return resp
            times=max(-1,times-1)
            fg=1
    if (fg):
        raise RetryCheckFailed(func.__qualname__,args,cfunc.__qualname__,resp)
    else:
        raise RetryExhausted(func.__qualname__,args,cfunc.__qualname__) from err

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

def TiebaRequest(url,data):
    req=Retry(requests.post,args=(url,),kwargs={"data":SignRequest(data)},\
        cfunc=(lambda x: x.status_code==200),ffunc=Progress.set_description,\
        fargs=("Connect Failed,Retrying...",),times=5)
    req.encoding='utf-8'
    ret=req.json()
    if (int(ret["error_code"])!=0):
        raise RequestError({"code":int(ret["error_code"]),"msg":str(ret["error_msg"])})
    return req.json()

def ReqContent(pid,fid,lz):
    if (~fid):
        return TiebaRequest(const.PageUrl,{"kz":str(pid),"pid":str(fid),"lz":str(int(lz)),"_client_version":"9.9.8.32"})
    else:
        return TiebaRequest(const.PageUrl,{"kz":str(pid),"lz":str(int(lz)),"_client_version":"9.9.8.32"})

def ReqComment(pid,fid,pn):
    return TiebaRequest(const.FloorUrl,{"kz":str(pid),"pid":str(fid),"pn":str(pn),"_client_version":"9.9.8.32"})

def FormatTime(t):
    return time.strftime("%Y-%m-%d %H:%M",time.localtime(int(t)))

def ProcessText(text,in_html):
    if (in_html):
        return html.escape(text)
    else:
        return html.escape(text).replace("\\","\\\\").replace("\n","  \n").replace("*","\\*")\
            .replace("-","\\-").replace("_","\\_").replace("(","\\(").replace(")","\\)")\
            .replace("#","\\#").replace("`","\\`").replace("~","\\~").replace("[","\\[")\
            .replace("]","\\]").replace("!","\\!").replace(".","\\.").replace("+","\\+")

def ProcessUrl(url,text):
    return '<a href="%s">%s</a>'%(url,text)

def ProcessImg(url):
    global ImgCount
    ImgCount+=1
    Pool.Download(url,"%d.jpg"%ImgCount)
    return '\n<div><img src="images/%d.jpg" /></div>\n'%ImgCount

def ProcessEmotion(name,text):
    if (len(name)==14):
        name+="1"
    name+=".png"
    if (not name in IsDownload):
        Pool.Download(const.EmotionUrl+name,name)
        IsDownload.add(name)
    return '<img src="images/%s" alt="%s" />'%(name,text)

def ProcessContent(data,in_html):
    content=""
    for s in data:
        if (str(s["type"])=="0"):
            content+=ProcessText(s["text"],in_html)
        elif (str(s["type"])=="1"):
            content+=ProcessUrl(s["link"],s["text"])
        elif (str(s["type"])=="2"):
            content+=ProcessEmotion(s["text"],s["c"])
        elif (str(s["type"])=="3"):
            content+=ProcessImg(s["origin_src"])
        elif (str(s["type"])=="4"):
            content+=ProcessText(s["text"],in_html)
        elif (str(s["type"])=="9"):
            content+=ProcessText(s["text"],in_html)
        elif (str(s["type"])=="11"):
            content+=ProcessImg(s["static"])
        elif (str(s["type"])=="20"):
            content+=ProcessImg(s["src"])
        else:
            raise UndifiedMsgType("content data wrong: \n%s\n"%str(s))
    return content

def ProcessFloor(floor,author,t,content):
    return '<hr />\n\n%s\n<div align="right" style="font-size:12px;color:#CCC;">\
        %s楼 | %s | %s</div>\n'%(content,floor,author,FormatTime(t))

def ProcessComment(author,t,content):
    return '%s | %s:<blockquote>%s</blockquote>'%(FormatTime(t),author,content)

def GetComment(pid,fid):
    Write('<pre style="background-color: #f6f8fa;border-radius: 3px;\
        font-size: 85%;line-height: 1.45;overflow: auto;padding: 16px;">')
    pn=1
    while (1):
        data=ReqComment(pid,fid,pn)
        data=data["subpost_list"]
        if (len(data)==0):
            break
        for comment in data:
            Write(ProcessComment(comment["author"]["name_show"],comment["time"],ProcessContent(comment["content"],1)))
        pn+=1
    Write('</pre>')

def ProcessUserList(data):
    userlist={}
    for user in data:
        userlist[user["id"]]={"id":user["portrait"].split("?")[0],"name":user["name_show"]}
    return userlist

def GetPost(pid,lz,comment):
    lastfid=-1
    content=""
    while (1):
        data=ReqContent(pid,lastfid,lz)
        print(data)
        userlist=ProcessUserList(data["user_list"])
        for floor in data["post_list"]:
            if (int(floor["id"])==lastfid):
                continue
            Progress.update(1)
            Progress.set_description("Collecting floor %s"%floor["floor"])
            fid=int(floor["id"])
            Write(ProcessFloor(floor["floor"],userlist[floor["author_id"]]["name"],floor["time"],ProcessContent(floor["content"],0)))
            if (int(floor["sub_post_number"])==0):
                continue
            if (comment):
                GetComment(pid,floor["id"])
        if (lastfid==fid):
            break
        # print(fid,lastfid)
        lastfid=fid
    return content
while (1):
    try:
        try:
            pid=int((Avalon.gets("请输入帖子链接或id:").split('/'))[-1].split('?')[0])
        except Exception:
            Avalon.warning("未找到正确的id")
            continue
        if (pid==0):
            exit(0)
        Avalon.info("id:%d"%pid)
    
        lz=Avalon.ask("只看楼主?",False)
        comment=(0 if lz else Avalon.ask("包括评论?",True))
        dirname=Avalon.gets("文件夹名(空则表示使用id):")
        if (len(dirname)==0):
            dirname=str(pid)
        Avalon.info("id:%d , 选定:%s && %s评论 , 目录:%s"%(pid,("楼主" if lz else "全部"),("全" if comment else "无"),dirname))
        if (not Avalon.ask("确认无误?",True)):
            Avalon.warning("请重新输入")
            continue
        Init(pid,dirname)
        FileHandle.write(GetPost(pid,lz,comment))
        Done()
    except KeyboardInterrupt:
        ForceStop()
        Avalon.error("Control-C,exiting",front="\n")
        exit(0)
    except UserCancelled:
        Avalon.warning("用户取消")
    except RequestError as err:
        err=err.data
        if (err["code"]==239105):
            Avalon.error("该贴子不存在或被删除",front="\n")
        else:
            Avalon.error("百度贴吧API返回错误,代码:%d\n描述:%s"%(err["code"],err["msg"]),front="\n")
    except Exception as err:
        ForceStop()
        Avalon.error("发生异常:\n"+traceback.format_exc(),front="\n")
        exit(0)
    else:
        Avalon.info("完成 %d"%pid)
        break