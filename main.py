# -*- coding: utf-8 -*-
"""
오늘의 일정(Google Calendar) + 할 일(Todoist) 브리핑 텔레그램 봇
"""
import os
import json
import requests
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ────────────── 설정(환경변수) ──────────────
BOT_TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID         = os.environ["TELEGRAM_CHAT_ID"]
TODOIST_TOKEN   = os.environ["TODOIST_TOKEN"]
GOOGLE_KEY_JSON = os.environ["GOOGLE_SA_JSON"]          # 서비스계정 JSON 전체
CALENDAR_ID     = os.environ.get("CALENDAR_ID", "primary")  # 보통 본인 Gmail 주소

KST  = timezone(timedelta(hours=9))
WEEK = ["월", "화", "수", "목", "금", "토", "일"]


# ────────────── Google Calendar: 오늘 일정 ──────────────
def get_events():
    info = json.loads(GOOGLE_KEY_JSON)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/calendar.readonly"])
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now   = datetime.now(KST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=1)

    res = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    lines = []
    for ev in res.get("items", []):
        title = ev.get("summary", "(제목 없음)")
        s = ev["start"].get("dateTime")
        if s:  # 시간 있는 일정
            t = datetime.fromisoformat(s).astimezone(KST).strftime("%H:%M")
            lines.append(f" • {t}  {title}")
        else:  # 종일 일정
            lines.append(f" • 종일  {title}")
    return lines


# ────────────── Todoist: 오늘 마감 할 일 ──────────────
def get_tasks():
    r = requests.get(
        "https://api.todoist.com/rest/v2/tasks",
        headers={"Authorization": f"Bearer {TODOIST_TOKEN}"},
        params={"filter": "today | overdue"},
        timeout=15,
    )
    r.raise_for_status()
    tasks = r.json()
    # 우선순위 높은 순(Todoist는 4가 최고 → P1)
    tasks.sort(key=lambda t: t.get("priority", 1), reverse=True)
    lines = []
    for t in tasks:
        p = {4: "P1", 3: "P2", 2: "P3", 1: "P4"}.get(t.get("priority", 1), "P4")
        lines.append(f" • [{p}] {t['content']}")
    return lines


# ────────────── 텔레그램 발송 ──────────────
def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=15,
    )
    if not r.ok:
        print("[telegram] 실패:", r.status_code, r.text)
    r.raise_for_status()


def main():
    now = datetime.now(KST)
    header = f"🌅 <b>오늘의 브리핑</b> ({now.strftime('%Y-%m-%d')} {WEEK[now.weekday()]})"

    try:
        events = get_events()
    except Exception as e:
        print("[calendar] 오류:", e)
        events = ["(캘린더를 불러오지 못했습니다)"]

    try:
        tasks = get_tasks()
    except Exception as e:
        print("[todoist] 오류:", e)
        tasks = ["(할 일을 불러오지 못했습니다)"]

    msg = [header, "─" * 15]
    msg.append("\n📅 <b>일정 (Google Calendar)</b>")
    msg += events if events else [" • 오늘 일정이 없습니다"]
    msg.append("\n✅ <b>할 일 (Todoist)</b>")
    msg += tasks if tasks else [" • 오늘 마감 할 일이 없습니다"]
    msg.append("\n오늘도 화이팅! 💪")

    send("\n".join(msg))
    print("발송 완료")


if __name__ == "__main__":
    main()
