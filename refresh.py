import requests
import json

def refresh_access_token(refresh_token):
    # 替换为实际的 Token 刷新接口地址
    token_url = "https://auth.openai.com/oauth/token" 
    
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        # "client_id": "YOUR_CLIENT_ID" # 如果服务端要求则取消注释
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(token_url, json=payload, headers=headers)
        response.raise_for_status() # 检查是否返回 200 OK
        
        new_tokens = response.json()
        print("✅ 续期成功！新的 Access Token:", new_tokens.get("access_token"))
        return new_tokens
        
    except requests.exceptions.RequestException as e:
        print("❌ 续期失败:", e)
        return None

# 使用你 JSON 中的 refresh_token 进行调用
my_refresh_token = "rt.1.AAByMyXYH-i2DbMGUjBWBFblzQjyclPyUxWBqsdGhGEOh5jj4yQ2bU38n9JbKgZicJtodikySM1s7tGZQbgBAdvU2l1_coP9XTKXk4PPJUMA-xvStOTrVTdQZawvUK5bvwHR4aAcIQjnmcpynV-g6Kpgw9I8JaNeMvrGMsFzkPXHhiJlXJBu0l3ZW4zotPqPtz-2PN7LEjnXpQIFjtsCnM_nNTHnOTsZbc5Pttd9uMcllAa9Ltyd4WIzWxgex3N48nrwJsAvkMpWqGNiAlMFB4oiksonQmForo7fIvVy9H8gY6ycAjYKgb8wZm8WqnIHsxI"
refresh_access_token(my_refresh_token)