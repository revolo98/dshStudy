import os
import datetime
import json
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')


def get_service():
    creds = None

    # GitHub Actions: 환경변수에서 토큰 로드
    token_json = os.environ.get('GOOGLE_TOKEN')
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

    # 로컬: 파일에서 토큰 로드
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)


def list_events(days=7, calendar_id='primary'):
    """앞으로 N일 간의 일정 조회"""
    service = get_service()
    now = datetime.datetime.now(datetime.UTC)
    end = now + datetime.timedelta(days=days)

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    if not events:
        print(f'향후 {days}일 간 일정이 없습니다.')
        return []

    print(f'\n--- 향후 {days}일 일정 ---')
    for i, event in enumerate(events, 1):
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"{i}. [{event['id'][:8]}...] {start} | {event['summary']}")
    return events


def add_event(summary, start_datetime, end_datetime, description='', calendar_id='primary'):
    """일정 추가

    Args:
        summary: 일정 제목
        start_datetime: 시작 시간 (예: '2026-03-30T10:00:00+09:00')
        end_datetime: 종료 시간 (예: '2026-03-30T11:00:00+09:00')
        description: 일정 설명 (선택)
    """
    service = get_service()
    event = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': start_datetime, 'timeZone': 'Asia/Seoul'},
        'end': {'dateTime': end_datetime, 'timeZone': 'Asia/Seoul'},
    }
    created = service.events().insert(calendarId=calendar_id, body=event).execute()
    print(f"일정 추가 완료: {created['summary']} (ID: {created['id'][:8]}...)")
    return created


def update_event(event_id, summary=None, start_datetime=None, end_datetime=None, description=None, calendar_id='primary'):
    """일정 수정

    Args:
        event_id: 수정할 일정의 ID (list_events로 확인)
        summary: 새 제목 (None이면 유지)
        start_datetime: 새 시작 시간 (None이면 유지)
        end_datetime: 새 종료 시간 (None이면 유지)
        description: 새 설명 (None이면 유지)
    """
    service = get_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    if summary:
        event['summary'] = summary
    if description is not None:
        event['description'] = description
    if start_datetime:
        event['start'] = {'dateTime': start_datetime, 'timeZone': 'Asia/Seoul'}
    if end_datetime:
        event['end'] = {'dateTime': end_datetime, 'timeZone': 'Asia/Seoul'}

    updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    print(f"일정 수정 완료: {updated['summary']} (ID: {updated['id'][:8]}...)")
    return updated


def delete_event(event_id, calendar_id='primary'):
    """일정 삭제"""
    service = get_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    print(f"일정 삭제 완료 (ID: {event_id[:8]}...)")


def list_calendars():
    """접근 가능한 전체 캘린더 목록 조회"""
    service = get_service()
    result = service.calendarList().list().execute()
    calendars = result.get('items', [])
    print('\n--- 접근 가능한 캘린더 목록 ---')
    for cal in calendars:
        print(f"[{cal['accessRole']}] {cal['summary']}")
        print(f"  ID: {cal['id']}")
    return calendars


def study_report(calendar_id, days=3):
    """공부 현황 리포트 (국어/영어/수학 기준, 일자별)"""
    service = get_service()
    now = datetime.datetime.now(datetime.UTC)
    start = now - datetime.timedelta(days=days)

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=start.isoformat(),
        timeMax=now.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    subjects = ['국어', '영어', '수학']

    # 날짜별로 그룹핑
    by_date = {}
    for event in events:
        title = event.get('summary', '')
        description = event.get('description', '') or ''
        matched = [s for s in subjects if s in title]
        if not matched:
            continue
        raw_date = event['start'].get('dateTime', event['start'].get('date'))
        date_key = raw_date[:10]  # YYYY-MM-DD
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append({
            'subject': matched[0],
            'title': title,
            'done': '완료' in description,
            'time': raw_date[11:16] if 'T' in raw_date else '',
        })

    print(f"\n{'='*40}")
    print(f"  공부 현황 리포트 (최근 {days}일)")
    print(f"{'='*40}")

    total_done = 0
    total_all = 0

    for date_key in sorted(by_date.keys()):
        items = by_date[date_key]
        day_done = sum(1 for i in items if i['done'])
        print(f"\n📅 {date_key} ({day_done}/{len(items)} 완료)")
        print(f"  {'-'*30}")
        for item in items:
            mark = '✅' if item['done'] else '❌'
            time_str = f" {item['time']}" if item['time'] else ''
            print(f"  {mark} [{item['subject']}] {item['title']}{time_str}")
        total_done += day_done
        total_all += len(items)

    if not by_date:
        print("\n  해당 기간에 공부 일정이 없습니다.")

    print(f"\n{'='*40}")
    overall = f"{total_done/total_all*100:.0f}%" if total_all > 0 else "일정없음"
    print(f"  전체 완료율: {overall} ({total_done}/{total_all})")
    print(f"{'='*40}\n")
    return by_date


def send_slack(message: str, webhook_url: str = ''):
    """Slack 메시지 전송"""
    url = webhook_url or os.environ.get('SLACK_WEBHOOK_URL', '')
    if not url:
        print("❌ Slack Webhook URL이 설정되지 않았습니다.")
        return
    res = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"text": message}, ensure_ascii=False).encode('utf-8')
    )
    if res.status_code == 200:
        print("✅ Slack 전송 완료!")
    else:
        print("❌ 전송 실패:", res.status_code, res.text)


def send_slack_blocks(blocks: list, webhook_url: str = ''):
    """Slack Block Kit 메시지 전송"""
    url = webhook_url or os.environ.get('SLACK_WEBHOOK_URL', '')
    if not url:
        print("❌ Slack Webhook URL이 설정되지 않았습니다.")
        return
    res = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"blocks": blocks}, ensure_ascii=False).encode('utf-8')
    )
    if res.status_code == 200:
        print("✅ Slack 전송 완료!")
    else:
        print("❌ 전송 실패:", res.status_code, res.text)


def mark_event_done(event_id, calendar_id='primary'):
    """이벤트 설명에 '완료' 추가"""
    service = get_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    description = event.get('description', '') or ''
    if '완료' not in description:
        event['description'] = (description + '\n완료').strip()
        service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    return event


def daily_schedule_blocks(calendar_id, name=''):
    """당일 공부 일정을 Slack Block Kit 형식으로 반환 (완료 버튼 포함)"""
    service = get_service()
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(kst).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + datetime.timedelta(days=1)

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=today.isoformat(),
        timeMax=tomorrow.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    subjects = ['국어', '영어', '수학']
    study_events = []

    for event in events:
        title = event.get('summary', '')
        matched = [s for s in subjects if s in title]
        if not matched:
            continue
        raw_start = event['start'].get('dateTime', event['start'].get('date'))
        time_str = raw_start[11:16] if 'T' in raw_start else '종일'
        description = event.get('description', '') or ''
        study_events.append({
            'id': event['id'],
            'subject': matched[0],
            'title': title,
            'time': time_str,
            'done': '완료' in description,
        })

    title_name = f"{name} " if name else ""
    date_str = today.strftime('%Y-%m-%d')
    done_count = sum(1 for e in study_events if e['done'])
    total = len(study_events)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📅 {title_name}오늘의 공부 일정 - {date_str}"}
        }
    ]

    if not study_events:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "오늘 공부 일정이 없습니다."}
        })
    else:
        for ev in study_events:
            mark = "✅" if ev['done'] else "⬜"
            section = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{mark} *[{ev['subject']}]* {ev['title']}  `{ev['time']}`"
                }
            }
            if not ev['done']:
                section["accessory"] = {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "완료 ✅"},
                    "style": "primary",
                    "action_id": f"mark_done_{ev['id']}",
                    "value": json.dumps({
                        "event_id": ev['id'],
                        "calendar_id": calendar_id,
                        "name": name
                    })
                }
            blocks.append(section)

        blocks.append({"type": "divider"})
        overall = f"{done_count/total*100:.0f}%" if total > 0 else "일정없음"
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📊 완료율: *{overall}* ({done_count}/{total})"
            }
        })

    return blocks


def study_report_text(calendar_id, days=3, name=''):
    """공부 현황 리포트 텍스트 반환 + 카카오톡 전송"""
    service = get_service()
    now = datetime.datetime.now(datetime.UTC)
    start = now - datetime.timedelta(days=days)

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=start.isoformat(),
        timeMax=now.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    subjects = ['국어', '영어', '수학']

    by_date = {}
    for event in events:
        title = event.get('summary', '')
        description = event.get('description', '') or ''
        matched = [s for s in subjects if s in title]
        if not matched:
            continue
        raw_date = event['start'].get('dateTime', event['start'].get('date'))
        date_key = raw_date[:10]
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append({
            'subject': matched[0],
            'title': title,
            'done': '완료' in description,
            'time': raw_date[11:16] if 'T' in raw_date else '',
        })

    title = f"{name} " if name else ""
    lines = [f"📚 {title}공부 현황 리포트 (최근 {days}일)\n"]
    total_done = 0
    total_all = 0

    for date_key in sorted(by_date.keys()):
        items = by_date[date_key]
        day_done = sum(1 for i in items if i['done'])
        lines.append(f"📅 {date_key} ({day_done}/{len(items)} 완료)")
        for item in items:
            mark = '✅' if item['done'] else '❌'
            time_str = f" {item['time']}" if item['time'] else ''
            lines.append(f"  {mark} [{item['subject']}] {item['title']}{time_str}")
        lines.append('')
        total_done += day_done
        total_all += len(items)

    if not by_date:
        lines.append("해당 기간에 공부 일정이 없습니다.")

    overall = f"{total_done/total_all*100:.0f}%" if total_all > 0 else "일정없음"
    lines.append(f"📊 전체 완료율: {overall} ({total_done}/{total_all})")

    message = "\n".join(lines)
    print(message)
    return message


CALENDAR_USERS = {
    'donghyun131013@gmail.com': '동현',
}

# 전체 일정(공부 필터 없음)을 슬랙으로 보낼 캘린더
SCHEDULE_USERS = {
    'revolo@gmail.com': '희성',
}


def daily_all_blocks(calendar_id, name=''):
    """당일 전체 일정을 Slack Block Kit 형식으로 반환"""
    service = get_service()
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(kst).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + datetime.timedelta(days=1)

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=today.isoformat(),
        timeMax=tomorrow.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    title_name = f"{name} " if name else ""
    date_str = today.strftime('%Y-%m-%d')

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📅 {title_name}오늘의 일정 - {date_str}"}
        }
    ]

    if not events:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "오늘 일정이 없습니다."}
        })
    else:
        for event in events:
            raw_start = event['start'].get('dateTime', event['start'].get('date'))
            time_str = raw_start[11:16] if 'T' in raw_start else '종일'
            summary = event.get('summary', '(제목 없음)')
            description = event.get('description', '') or ''
            desc_str = f"\n└ {description.strip()}" if description.strip() else ''
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• *{time_str}* {summary}{desc_str}"
                }
            })

    return blocks


def daily_schedule_text(calendar_id, name=''):
    """당일 일정 조회 후 슬랙 메시지 텍스트 반환"""
    service = get_service()
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(kst).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + datetime.timedelta(days=1)

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=today.isoformat(),
        timeMax=tomorrow.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    title = f"{name} " if name else ""
    date_str = today.strftime('%Y-%m-%d (%a)')
    lines = [f"📅 {title}오늘의 일정 - {date_str}\n"]

    if not events:
        lines.append("오늘 일정이 없습니다.")
    else:
        for event in events:
            raw_start = event['start'].get('dateTime', event['start'].get('date'))
            time_str = raw_start[11:16] if 'T' in raw_start else '종일'
            summary = event.get('summary', '(제목 없음)')
            description = event.get('description', '') or ''
            desc_str = f"\n    └ {description.strip()}" if description.strip() else ''
            lines.append(f"  • {time_str} {summary}{desc_str}")

    return "\n".join(lines)


if __name__ == '__main__':
    print("=== 공부 현황 확인 ===")
    for calendar_id, name in CALENDAR_USERS.items():
        msg = study_report_text(calendar_id=calendar_id, days=3, name=name)
        send_slack(msg)

    # 2. 일정 추가 예시 (주석 해제 후 사용)
    # add_event(
    #     summary='테스트 회의',
    #     start_datetime='2026-03-30T10:00:00+09:00',
    #     end_datetime='2026-03-30T11:00:00+09:00',
    #     description='Google Calendar API 테스트'
    # )

    # 3. 일정 수정 예시 (event_id는 list_events 결과에서 확인)
    # update_event(
    #     event_id='여기에_이벤트_ID_입력',
    #     summary='수정된 회의 제목'
    # )

    # 4. 일정 삭제 예시
    # delete_event(event_id='여기에_이벤트_ID_입력')
