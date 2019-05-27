import aiohttp
import asyncio
import time
import threading
from tqdm import tqdm
from functools import wraps

class RetryExhaustedError(Exception):pass

def retry(*exceptions,retries=5,cooldown=1,verbose=True):
    def wrap(func):
        @wraps(func)
        async def inner(*args,**kwargs):
            retries_count = 0
            while (1):
                try:
                    result = await func(*args,**kwargs)
                except exceptions as err:
                    retries_count += 1
                    if (retries_count>retries):
                        verbose
                        raise RetryExhaustedError(func.__qualname__,args,kwargs) \
                            from err
                    else:
                        verbose
                    if (cooldown):
                        await asyncio.sleep(cooldown)
                else:
                    return result
        return inner
    return wrap

class DownloadPool():
    def __init__(self,dir="",unit="it"):
        self.Dir=dir
        self.ImgProc=tqdm(unit=unit,ascii=True)
        self.Running=0
        self.Start()

    def StartLoop(self,loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def StopLoop(self,loop):
        asyncio.run_coroutine_threadsafe(self.CheckDone(self.DownLoop),self.DownLoop)
    
    def Start(self):
        self.DownLoop=asyncio.new_event_loop()
        self.DownThread=threading.Thread(target=self.StartLoop,args=(self.DownLoop,))
        self.DownThread.setDaemon(True)
        self.DownThread.start()

    def Stop(self):
        self.StopLoop(self.DownLoop)
        while (self.DownLoop.is_running()):
            time.sleep(0.5)
        self.ImgProc.close()

    async def GetRaw(self,session,url):
        async with session.get(url) as resp:
            return await resp.read()

    @retry(aiohttp.ClientError)
    async def AsyncDownload(self,url,filename):
        self.Running+=1
        async with aiohttp.ClientSession() as session:
            self.ImgProc.set_description("Downloading %s"%filename)
            raw=await self.GetRaw(session,url)
            self.ImgProc.set_description("Downloading %s"%filename)
            with open(self.Dir+filename,"wb") as f:
                f.write(raw)
        self.ImgProc.update(1)
        self.Running-=1

    def Download(self,url,filename):
        asyncio.run_coroutine_threadsafe(self.AsyncDownload(url,filename),self.DownLoop)

    async def CheckDone(self,loop):
        while (self.Running!=0):
            await asyncio.sleep(2)
        loop.stop()
