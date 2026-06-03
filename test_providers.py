"""测试 .env 中配置的 LLM Provider 是否可用"""
import sys, os, re, requests, warnings, urllib3

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'

warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv = os.path.join(SCRIPT_DIR, '.env')
with open(dotenv, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

providers = []

zk = os.environ.get('ZHIPU_API_KEY', '')
if zk:
    providers.append({
        'name': '智谱',
        'api_key': zk,
        'api_base': os.environ.get('ZHIPU_API_BASE', 'https://open.bigmodel.cn/api/paas/v4/chat/completions'),
        'model': os.environ.get('ZHIPU_MODEL', 'glm-4-flash'),
    })

mk = os.environ.get('MINIMAX_API_KEY', '')
if mk:
    providers.append({
        'name': 'MiniMax',
        'api_key': mk,
        'api_base': os.environ.get('MINIMAX_API_BASE', 'https://api.minimaxi.chat/v1/text/chatcompletion_v2'),
        'model': os.environ.get('MINIMAX_MODEL', 'MiniMax-Text-01'),
    })

ok = os.environ.get('OPENROUTER_API_KEY', '')
if ok:
    providers.append({
        'name': 'OpenRouter',
        'api_key': ok,
        'api_base': os.environ.get('OPENROUTER_API_BASE', 'https://openrouter.ai/api/v1/chat/completions'),
        'model': os.environ.get('OPENROUTER_MODEL', 'deepseek/deepseek-v4-flash:free'),
    })

print(f'可用 providers: {[p["name"] for p in providers]}')
print()

prompt = '用户在聊天室说: 嘿你好。请以聊天室角色的身份简短回复1-2句话。'
msgs = [
    {'role': 'system', 'content': '你是一个聊天室里的角色。简短自然，1-2句话，不要markdown，不要引号。'},
    {'role': 'user', 'content': prompt}
]

for p in providers:
    tag = p['name']
    short = p['model'].split('/')[-1]
    print(f'测试 {tag}/{short} ...')
    try:
        resp = requests.post(
            p['api_base'],
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {p["api_key"]}'
            },
            json={
                'model': p['model'],
                'messages': msgs,
                'max_tokens': 100,
                'temperature': 0.9
            },
            timeout=30,
            verify=False
        )
        data = resp.json()
        if data.get('error'):
            err = str(data['error'].get('message', ''))[:100]
            print(f'  ❌ {err}')
        elif data.get('choices'):
            text = data['choices'][0]['message']['content'].strip()
            text = re.sub(r'[*#`"\u201c\u201d]', '', text)
            print(f'  ✅ {text}')
        else:
            print(f'  ❌ 未知响应: {str(data)[:120]}')
    except Exception as e:
        print(f'  ❌ {e}')
    print()

print('测试完成！')
