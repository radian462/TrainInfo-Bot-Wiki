from atproto import Client,models
import time
import datetime
import requests
import re
import redis
import os
import json

r = redis.Redis(
  host='apn1-probable-gator-33492.upstash.io',
  port=33492,
  password= os.getenv("upstash_passward"),
  ssl=True
)

client = Client()
client.login("train-kanto.f5.si", os.getenv("password"))

second = datetime.datetime.now().time().second
time.sleep(60 - second)

old_message = ""

def get_traindata():
  try:
    site_source = requests.get("https://mainichi.jp/traffic/etc/a.html").text
    site_source = re.sub("\n" , "#" , site_source)

    site_data = re.search(r'関東エリア(.*?)<td colspan="3">', site_source).group(1)
    site_data = re.sub("#" , "\n" , site_data)

    train = re.findall(r'<td height="40"><font size="-1">(.*?)<BR><strong>', site_data)
    status = re.findall(r'>(.*?)</font></strong></font></td>', site_data)
    info = re.findall(r'<td height="40"><font size="-1">(.*?)</font></td>', site_data)
  except:
    response = requests.get("https://www.yomiuri.co.jp/traffic/area04/").text
    response = re.sub(" ","",response)
    response = re.sub("\n","#",response)

    site_data = re.search(r'<h1class="p-header-category-current-title">関東</h1>(.*?)<divclass="layout-contents__sidebar">', response).group(1)
    site_data = re.sub("#" , "\n" , site_data)

    train = re.findall(r'(.*?)<spanclass="traffic-area-wrap-mass__info--', site_data)
    status = re.findall(r'">(.*?)</span>\n</h4>', site_data)
    info = re.findall(r'<p>(.*?)</p>\n</article>',site_data)

  emojidict = {"列車遅延": "🕒列車遅延", "運転見合わせ": "🛑運転見合わせ", "運転情報": "ℹ️運転情報", "運転状況": "ℹ️運転状況", "運転再開":"🚋運転再開","平常運転":"🚋平常運転","運転計画":"🗒️運転計画","その他":"⚠️その他"}

  for i in range(len(status)):
    if "運転計画" in status[i]:
      status[i] = "運転計画"

  status = [emojidict.get(s, emojidict["その他"]) for s in status]
  data = [{"train": t, "status": s, "info": i} for t, s, i in zip(train, status, info)]

  return data


def merge_data(olddata,newdata):
  olddata_trains = [d["train"] for d in olddata]
  newdata_trains = [d["train"] for d in newdata]

  showdata = []
  for i, train in enumerate(newdata_trains):
    info = newdata[i]["info"]
    if train in olddata_trains:
      j = olddata_trains.index(train)
      newstatus = newdata[i]["status"]
      oldstatus = olddata[j]["status"]
    else:
      newstatus = newdata[i]["status"]
      oldstatus = "🚋平常運転"

    data = {"train":train,"oldstatus":oldstatus,"newstatus":newstatus,"info":info}
    showdata.append(data)

  for train in set(olddata_trains) - set(newdata_trains): 
    i = olddata_trains.index(train)
    newstatus = "🚋平常運転"
    oldstatus = olddata[i]["status"]
    info = "現在、ほぼ平常通り運転しています。"

    data = {"train":train,"oldstatus":oldstatus,"newstatus":newstatus,"info":info}
    showdata.append(data)

  return showdata

def make_message():
  olddata = r.get('kanto_train')
  olddata = json.loads(olddata)
  newdata = get_traindata()

  json_newdata = json.dumps(newdata)
  r.set("kanto_train", json_newdata)

  data = merge_data(olddata,newdata)
  data_trains = [d["train"] for d in data]

  message = ""
  for train in data_trains:
      t = data_trains.index(train)
      if olddata == newdata:
          message = "運行状況に変更はありません。"
      else:
        if data == []:
          message = "関東の電車は全て正常に動いています"
        if data[t]["oldstatus"] == data[t]["newstatus"]:
          if data[t]["oldstatus"] != "🚋平常運転":
             message += f'{data[t]["train"]} : {data[t]["newstatus"]}\n{data[t]["info"]}\n\n'
        elif data[t]["oldstatus"] != data[t]["newstatus"]:
          message += f'{data[t]["train"]} : {data[t]["oldstatus"]}➡️{data[t]["newstatus"]}\n{data[t]["info"]}\n\n'

  while message.endswith('\n'):
    message= message[:-1]

  uri = r.get('kanto_train_uri').decode('utf-8').strip('"') 
  post_data = client.get_posts([uri])
  try:
    post_text = re.search(r"text='(.*?)'", str(post_data)).group(1)
    if post_text == "運行状況に変更はありません。":
      client.delete_post(uri)
  except:
    pass

  return message

def fixed_post():
  client.unrepost("at://did:plc:f2nbethp4g7xfdthyv2wipjo/app.bsky.feed.post/3klqfg7fbia2z")
  client.repost("at://did:plc:f2nbethp4g7xfdthyv2wipjo/app.bsky.feed.post/3klqfg7fbia2z","bafyreidpslbv6vp3ghpyw7c74s7hhkc7coylelzq24dfvyo5ghcnqgplwi")


while True:
    current_time = time.localtime()
    minutes = current_time.tm_min
    print(minutes)

    if minutes in [0,10,20,30,40,50,60]:
      message = make_message()
      message_list = [] 
      sentence = "" 

      for i in re.split(r"(?<=\n\n)", message): 
        if len(sentence) + len(i) <= 300: 
          sentence += i 
        else: 
          message_list.append(sentence) 
          sentence = i 

      message_list.append(sentence) 
      
      for i in message_list: 
        while i.endswith('\n'):
          i = i[:-1]
        print(len(i))

      for m in message_list:
        if message_list.index(m) == 0:  
          post = client.send_post(m)
          root_post_ref = models.create_strong_ref(post)
        elif message_list.index(m) == 1:
          reply_to_root = models.create_strong_ref(
              client.send_post(
                  text= m,
                  reply_to=models.AppBskyFeedPost.ReplyRef(parent=root_post_ref,root=root_post_ref),
              )
          )
        else:
          reply_to_root = models.create_strong_ref(
              client.send_post(
                  text= m,
                  reply_to=models.AppBskyFeedPost.ReplyRef(parent=reply_to_root,root=root_post_ref),
              )
          )

      r.set("kanto_train_uri", post.uri)
      fixed_post()
      
    time.sleep(60-datetime.datetime.now().time().second)
