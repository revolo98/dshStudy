"""
Vercel 서버리스 함수: Slack 인터랙티브 버튼 처리
- 완료 버튼 클릭 → Google Calendar 이벤트 완료 표시 → Slack 메시지 업데이트
"""
import hashlib
import hmac
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs

import requests

# 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google_calendar import mark_event_done, mark_sub_item_done, daily_schedule_blocks, daily_all_blocks


def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    signing_secret = os.environ.get('SLACK_SIGNING_SECRET', '').strip().encode('utf-8')
    if not signing_secret:
        print("[ERROR] SLACK_SIGNING_SECRET 환경변수 없음")
        return False
    base_string = f"v0:{timestamp}:{body.decode('utf-8')}".encode('utf-8')
    computed = 'v0=' + hmac.new(signing_secret, base_string, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        timestamp = self.headers.get('X-Slack-Request-Timestamp', '')
        signature = self.headers.get('X-Slack-Signature', '')

        # 리플레이 공격 방지 (5분 이내 요청만 허용)
        try:
            if abs(time.time() - int(timestamp)) > 300:
                print(f"[ERROR] 요청 시간 초과: timestamp={timestamp}")
                self._respond(400, 'Request too old')
                return
        except (ValueError, TypeError) as e:
            print(f"[ERROR] timestamp 파싱 실패: {e}, timestamp={timestamp!r}")
            self._respond(400, 'Invalid timestamp')
            return

        if not verify_slack_signature(body, timestamp, signature):
            print(f"[ERROR] Slack 서명 검증 실패: signature={signature!r}")
            self._respond(401, 'Invalid signature')
            return

        try:
            params = parse_qs(body.decode('utf-8'))
            payload = json.loads(params['payload'][0])
        except (KeyError, json.JSONDecodeError) as e:
            print(f"[ERROR] payload 파싱 실패: {e}\nbody={body[:500]!r}")
            self._respond(400, 'Invalid payload')
            return

        if payload.get('type') == 'block_actions':
            actions = payload.get('actions', [])
            if actions:
                action = actions[0]
                action_id = action.get('action_id', '')
                print(f"[INFO] action_id={action_id!r}")

                response_url = payload.get('response_url', '')

                def reply_error(msg):
                    print(f"[ERROR] {msg}")
                    if response_url:
                        requests.post(response_url, json={"text": f"❌ 오류: {msg}"})

                def trigger_github_workflow(workflow_file):
                    github_token = os.environ.get('GITHUB_TOKEN', '')
                    github_repo = os.environ.get('GITHUB_REPO', 'revolo98/dshStudy')
                    url = f"https://api.github.com/repos/{github_repo}/actions/workflows/{workflow_file}.yml/dispatches"
                    print(f"[INFO] GitHub API 요청: {url}, 토큰={'있음' if github_token else '없음'}")
                    resp = requests.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {github_token}",
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28"
                        },
                        json={"ref": "main"}
                    )
                    print(f"[INFO] GitHub API 응답: {resp.status_code} {resp.text}")
                    return resp.status_code, resp.text, bool(github_token)

                if action_id.startswith('mark_done_'):
                    try:
                        value = json.loads(action['value'])
                        event_id = value['event_id']
                        calendar_id = value['calendar_id']
                        name = value.get('name', '')

                        mark_event_done(event_id, calendar_id)

                        updated_blocks = daily_schedule_blocks(calendar_id, name)
                        if response_url:
                            requests.post(response_url, json={
                                "replace_original": True,
                                "blocks": updated_blocks
                            })
                    except Exception as e:
                        reply_error(f"{e}\n{traceback.format_exc()}")

                elif action_id.startswith('mark_item_'):
                    try:
                        value = json.loads(action['value'])
                        event_id = value['event_id']
                        calendar_id = value['calendar_id']
                        name = value.get('name', '')
                        item_text = value['item_text']
                        func = value.get('func', 'study')

                        mark_sub_item_done(event_id, item_text, calendar_id)

                        if func == 'schedule':
                            updated_blocks = daily_all_blocks(calendar_id, name)
                        else:
                            updated_blocks = daily_schedule_blocks(calendar_id, name)

                        if response_url:
                            requests.post(response_url, json={
                                "replace_original": True,
                                "blocks": updated_blocks
                            })
                    except Exception as e:
                        reply_error(f"{e}\n{traceback.format_exc()}")

                elif action_id.startswith('trigger_workflow_'):
                    try:
                        workflow_name = action.get('value', '')
                        status, resp_body, has_token = trigger_github_workflow(workflow_name)
                        if status == 204:
                            label = '📊 공부 리포트' if workflow_name == 'study_report' else '🔄 일정 알림'
                            if response_url:
                                requests.post(response_url, json={
                                    "response_type": "ephemeral",
                                    "text": f"✅ {label} 워크플로우 실행 요청 완료! 잠시 후 메시지가 전송됩니다."
                                })
                        else:
                            token_hint = "토큰없음" if not has_token else "토큰있음"
                            reply_error(f"GitHub API {status} ({token_hint}): {resp_body}")
                    except Exception as e:
                        reply_error(f"{e}\n{traceback.format_exc()}")

                else:
                    print(f"[WARN] 처리되지 않은 action_id: {action_id!r}")
        else:
            print(f"[WARN] 처리되지 않은 payload type: {payload.get('type')!r}")

        self._respond(200, '')

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def log_message(self, format, *args):
        print(f"[HTTP] {format % args}")
