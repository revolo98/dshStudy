import requests
import webbrowser

REST_API_KEY = 'a721c96b55df6f9fcbb9f6a837060b99'
REDIRECT_URI = 'https://localhost'

def get_auth_code():
    url = (
        f"https://kauth.kakao.com/oauth/authorize"
        f"?client_id={REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
    )
    print("브라우저에서 카카오 로그인 후 리다이렉트된 URL을 복사해주세요.")
    print(f"\n아래 URL이 자동으로 열립니다:\n{url}\n")
    webbrowser.open(url)
    redirected_url = input("리다이렉트된 전체 URL 붙여넣기: ").strip()
    code = redirected_url.split("code=")[-1].split("&")[0]
    return code

def get_tokens(auth_code):
    res = requests.post("https://kauth.kakao.com/oauth/token", data={
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": auth_code,
    })
    tokens = res.json()
    if 'access_token' not in tokens:
        print("오류:", tokens)
        return None
    # 토큰 저장
    with open("kakao_token.txt", "w") as f:
        f.write(tokens['access_token'] + "\n")
        f.write(tokens.get('refresh_token', '') + "\n")
    print("✅ 토큰 발급 완료! kakao_token.txt 저장됨")
    return tokens

if __name__ == '__main__':
    code = get_auth_code()
    get_tokens(code)
