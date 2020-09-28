from celery.result import AsyncResult
from django.shortcuts import render
from django.http import HttpResponse
from .tasks import handle_user
import time

taskmap = {}

def start_user(request):
    uid = request.GET["uid"]
    if uid in taskmap:
        if not taskmap[uid].ready():
            return HttpResponse("Still querying!")
        if not all([AsyncResult(c).ready() for c in taskmap[uid].result]):
            return HttpResponse("Still running!")
    task = handle_user.delay(uid)
    taskmap[uid] = task
    return HttpResponse("Queued!")

# Create your views here.
def index(request):
    tasks = taskmap[request.GET['uid']]
    taskdict = {}
    taskdict["main"] = tasks
    if tasks.ready():
        for i, c in enumerate(tasks.result):
            taskdict[i] = c
    return render(request, 'demo_app/index.html', context={'celery_task_ids': taskdict})
