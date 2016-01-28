import poplib
import ConfigParser
import re
import smtplib
import sqlite3
import hashlib
import sys

from email.mime.text import MIMEText
from email.parser import Parser
from email.Utils import formatdate

import chardet

config = ConfigParser.ConfigParser()
config.read("bacon.cfg")

conn = sqlite3.connect('bacon.db')
c = conn.cursor()


def get_urls(data):
    return re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', data)


def have_replied(mail_id):
    c.execute('''UPDATE spam SET replied = 1 WHERE id = ?''', (str(mail_id),))
    conn.commit()


def reply(to, subj, body):
    msg = MIMEText("Hello, how can I help you?" + "\n\n" + body.encode("UTF-8"))
    msg["From"] = config.get('account', 'username')
    msg["To"] = to
    msg["Subject"] = "Re: " + subj
    msg['Date'] = formatdate(localtime=True)
    server = smtplib.SMTP(config.get('server', 'smtp_host'))
    try:
        server.sendmail(msg["From"], msg["To"], msg.as_string())
    except:
        print "Error sending mail"
    server.quit()
    print "Send message to", to


def store_data(data):
    c.execute('''CREATE TABLE IF NOT EXISTS spam (id int UNIQUE ON CONFLICT IGNORE, sender text, subject text, body text, urls text, replied int)''')
    conn.commit()
    c.execute('''INSERT INTO spam VALUES (?,?,?,?,?,?)''', data)
    conn.commit()


def already_replied(mail_id):
    rep = c.execute("""SELECT replied FROM spam WHERE id = ?""", (str(mail_id),)).fetchone()[0]
    if rep == 1:
        return True
    else:
        False


def db_stats():
    print "Mails in DB:",
    print c.execute('''SELECT COUNT(id) FROM spam''').fetchone()[0]


M = poplib.POP3(config.get('server', 'hostname'))
M.set_debuglevel(0)
M.user(config.get('account', 'username'))
M.pass_(config.get('account', 'password'))

print M.getwelcome()
print "Mails in inbox:", M.stat()

max_id = c.execute("""SELECT MAX(id) AS max_id FROM spam""").fetchone()[0]

if max_id == len(M.list()[1]):
    db_stats()
    print "No new mails to process... Exiting"
    sys.exit()

for i in range(max_id + 1, len(M.list()[1]) + 1):
    message = M.retr(i)
    message = "\n".join(message[1])
    message = Parser().parsestr(message)
    if not "subject" in message:
        message["subject"] = "None"
    if len(message["subject"]) > 43:
        pass
    else:
        pass
    for part in message.walk():
        if part.get_content_type():
            if part.get_content_type() in ["text/plain", "text/html"]:
                body = part.get_payload(decode=True)
            elif part.get_content_type() in ["image/jpeg", "image/gif", "image/png", "image/pjpeg", "image/bmp"]:
                image = part.get_payload(decode=True)
                name = hashlib.md5(image).hexdigest()
                with open("bins/img/" + name, "wb") as img_file:
                    img_file.write(image)
            elif "application" in part.get_content_type():
                app = part.get_payload(decode=True)
                name = hashlib.md5(app).hexdigest()
                with open("bins/application/" + name, "wb") as app_file:
                    app_file.write(app)
            elif "audio" in part.get_content_type():
                audio = part.get_payload(decode=True)
                name = hashlib.md5(audio).hexdigest()
                with open("bins/audio/" + name, "wb") as audio_file:
                    audio_file.write(audio)
            elif "text/calendar" in part.get_content_type():
                ical = part.get_payload(decode=True)
                name = hashlib.md5(ical).hexdigest()
                with open("bins/ical/" + name, "wb") as ical_file:
                    ical_file.write(ical)
            elif part.get_content_type() in ["multipart/alternative",
                                             "multipart/mixed",
                                             "multipart/related",
                                             "message/delivery-status",
                                             "message/rfc822",
                                             "multipart/report",
                                             "text/richtext",
                                             "message/disposition-notification",
                                             ]:
                continue
            else:
                print part.get_content_type()

    result = chardet.detect(body)
    if not type(body) == unicode:
        if not result['encoding']:
            result['encoding'] = "ascii"
        body = unicode(body, result['encoding'], "ignore")
    urls = get_urls(body)
    set(urls)
    urls = ",".join(urls)
    if "MAILER-DAEMON@" in message["from"] or "postmaster@" in message["from"] or "root@" in message["from"]:
        M.dele(i)
    else:
        store_data((i, message["from"].decode('unicode-escape'),
                    message["subject"].decode('unicode-escape'),
                    body, urls, 0))
        if not already_replied(i):
            try:
                reply(message["from"], message["subject"], body)
            except:
                raise
            else:
                have_replied(i)

M.quit()
print
db_stats()
url_set = set()
with open("urls.txt", "wb") as url_file:
    for urlblob in c.execute('''SELECT urls FROM spam''').fetchall():
        new_urls = filter(lambda url: url.startswith('http'), filter(None, urlblob[0].split(",")))
        url_set.update(new_urls)
    set(url_set)
    print "Total unique URLs from mails:", len(url_set)
    [url_file.write(url + "\n") for url in url_set]
conn.close()
