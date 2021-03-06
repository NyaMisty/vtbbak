import aria2p
from celery import shared_task
from celery.utils.log import get_task_logger
from celery_progress.backend import ProgressRecorder
import os
import re
import time
import requests
from config import CONFIG

logger = get_task_logger(__name__)
sess = requests.Session()
sess.headers = {
    "Cookie": CONFIG['cookie']
}
WORKDIR = CONFIG['workdir']

aria2 = aria2p.API(
    aria2p.Client(
        host="http://localhost",
        port=6800,
        secret=""
    )
)

@shared_task(bind=True)
def handle_user(self, uid):
    progress_recorder = ProgressRecorder(self)

    vlist = []
    p = 1
    while True:
        logger.info("retriving video list page %d" % p)
        resp = sess.get(
            'https://api.bilibili.com/x/space/arc/search?mid={}&ps=100&tid=0&pn={}&keyword=&order=pubdate'.format(
                uid, p))
        if resp.status_code != 200:
            logger.warn("video list failed status: %d", resp.status_code)
            return
        resp = resp.json()
        if resp['data']['list']['vlist'] == []:
            logger.info("finished retriving video list!")
            break
        p += 1
        vlist += resp['data']['list']['vlist']
        progress_recorder.set_progress(0, p, description="retriving video list page %d" % p)

    workdir = os.path.join(WORKDIR, str(uid))
    tasks = []
    for i, video in enumerate(vlist):
        vtask = process_video(workdir, video['bvid'])
        progress_recorder.set_progress(i, len(vlist), description="retriving video info %d: %s" % (i, video['bvid']))
        tasks += vtask

    # self.update_state(state="PROGRESS", meta={'tasks': [c.id for c in tasks]})
    return tasks

@shared_task(bind=True)
def process_video(self, dir, bvid):
    logger.info("retriving video info %s" % bvid)
    videopath = os.path.join(dir, bvid)
    if not os.path.exists(videopath):
        os.makedirs(videopath)
    r = sess.get("https://api.bilibili.com/x/web-interface/view/detail?bvid=%s&web_rm_repeat=" % bvid)
    if r.status_code != 200:
        raise Exception("get video detail %s failed with status %d", bvid, r.status_code)
    metatext = r.text
    meta = r.json()
    aid = meta['data']['View']['aid']
    r = sess.get("https://api.bilibili.com/x/v2/reply?pn=1&type=1&oid=%s&sort=2&_=1601249894421" % aid)
    if r.status_code != 200:
        raise Exception("get video reply %s failed with status %d", bvid, r.status_code)
    replytext = r.text

    pic = sess.get(meta['data']['View']['pic']).content

    with open(os.path.join(videopath, "meta.json"), 'w') as f:
        f.write(metatext)
    with open(os.path.join(videopath, "reply.json"), 'w') as f:
        f.write(replytext)
    with open(os.path.join(videopath, "pic.jpg"), 'wb') as f:
        f.write(pic)


    download_tasks = []
    title = meta['data']['View']['title']
    for i,page in enumerate(meta['data']['View']['pages']):
        task = download_video.delay(videopath, bvid, i + 1, page['cid'], "%s-%s" % (title, page['part']))
        download_tasks.append(task)
    return [c.id for c in download_tasks]

class Aria2Exception(Exception):
    pass

@shared_task(bind=True, autoretry_for=(Aria2Exception, ))
def download_video(self, dir, bvid, pn, cid, desc):
    workdir = os.path.join(dir, "P%d" % pn)
    if not os.path.exists(workdir):
        os.makedirs(workdir)

    progress_recorder = ProgressRecorder(self)
    videodesc = ' %s P%d %s, cid: %s' % (bvid, pn, desc, cid)
    def report_progress(cur, msg):
        progress_recorder.set_progress(cur, 100, description=msg + videodesc)
    while len(aria2.client.tell_active()) > 10:
        report_progress(0, 'waiting for queue to smaller...')
        time.sleep(20)

    videoUrl = audioUrl = None
    for i in range(10):
        try:
            report_progress(0, 'trying to get playurl for')
            r = sess.get("https://api.bilibili.com/x/player/playurl?cid=%s&bvid=%s&qn=116&type=&otype=json&fourk=1&fnver=0&fnval=80" % (cid, bvid))
            if r.json()['code'] != 0:
                logger.warn("failed to retrive playurl for %s P%d cid %s" % (bvid, pn, cid))
                progress_recorder.set_progress(0, 100,
                                               description='error during  %s P%d, cid: %s' % (bvid, pn, cid))
                time.sleep(60)
                continue
            videoUrl = r.json()['data']['dash']['video'][0]['baseUrl'].replace("https://", "http://")
            audioUrl = r.json()['data']['dash']['audio'][0]['baseUrl'].replace("https://", "http://")
            if videoUrl.startswith('http://upos-sz-mirror'):
                videoUrl, _ = re.subn(r'upos-sz-mirror([a-z0-9]+?).bilivideo.com', CONFIG['prefer_cdn'] , videoUrl, 1)
                audioUrl, _ = re.subn(r'upos-sz-mirror([a-z0-9]+?).bilivideo.com', CONFIG['prefer_cdn'], audioUrl, 1)
                break
            else:
                logger.info("not receiving upos cdn, got %s instead for %s P%d cid %s" % (videoUrl, bvid, pn, cid))
        except Exception as e:
            pass
        time.sleep(2)

    if not videoUrl:
        raise Exception("failed to retrive videoUrl!!")

    danmakuUrl = 'http://comment.bilibili.com/%s.xml' % cid
    for i in range(5):
        try:
            r = sess.get(danmakuUrl)
            if not r.content.startswith(b"<"):
                continue
            with open(os.path.join(workdir, "%s-P%d-%s-danmaku.xml" % (bvid, pn, cid)), "wb") as f:
                f.write(r.content)
            break
        except Exception as e:
            import traceback; traceback.print_exc()
            if i == 4:
                raise

    headers = '\n'.join([
        'Referer: https://www.bilibili.com/video/%s' % (bvid),
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36',
        'Origin: https://www.bilibili.com',
        'Accept: */*',
        #'Accept-Encoding: gzip, deflate, br',
        'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8'
    ])
    vopt = aria2.get_global_options()
    vopt.dir = workdir
    vopt.out = "%s-P%d-%s-v.m4s" % (bvid, pn, cid)
    vopt.header = headers
    vdownload = aria2.add_uris([videoUrl], vopt)

    aopt = aria2.get_global_options()
    aopt.dir = workdir
    aopt.out = "%s-P%d-%s-a.m4s" % (bvid, pn, cid)
    aopt.header = headers
    adownload = aria2.add_uris([audioUrl], aopt)

    '''
    dopt = aria2.get_global_options()
    dopt.dir = workdir
    dopt.out = "%s-P%d-%s-danmaku.xml" % (bvid, pn, cid)
    dopt.header = headers
    ddownload = aria2.add_uris([danmakuUrl], dopt)
    '''

    while True:
        time.sleep(1)
        try:
            vdownload.update()
            adownload.update()
            #ddownload.update()
            if vdownload.is_active or vdownload.is_waiting:
                report_progress(vdownload.progress * 0.9 + adownload.progress * 0.1 - 0.01, 'downloading video, speed: %s' % vdownload.download_speed_string())
            else:
                report_progress(vdownload.progress * 0.9 + adownload.progress * 0.1 - 0.01, 'downloading audio, speed: %s' % adownload.download_speed_string())
                if not (adownload.is_active or adownload.is_waiting):
                    '''
                    report_progress(vdownload.progress * 0.9 + adownload.progress * 0.1 - 0.01,
                                    'downloading danmaku, speed: %s' % ddownload.download_speed_string())
                    if not (ddownload.is_active or ddownload.is_waiting):
                        logger.info("finished downloading %s P%d cid %s" % (bvid, pn, cid))
                        if vdownload.is_complete and adownload.is_complete and ddownload.is_complete:
                            return "Successfully" + " download" + videodesc # else "failed to"
                        else:
                            raise Aria2Exception("Aria2 failed to download something, status: %s %s %s" % (vdownload.is_complete, adownload.is_complete, ddownload.is_complete))
                     '''
                    logger.info("finished downloading %s P%d cid %s" % (bvid, pn, cid))
                    if vdownload.is_complete and adownload.is_complete:
                        return "Successfully" + " download" + videodesc  # else "failed to"
                    else:
                        raise Aria2Exception("Aria2 failed to download something, status: %s %s" % (vdownload.is_complete, adownload.is_complete))
        except Aria2Exception:
            raise
        except Exception as e:
            raise Aria2Exception("Failed to query to aria2 because: %s" % e)
